from __future__ import annotations

import base64
import json
import hashlib
import logging
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


log = logging.getLogger(__name__)


class GitHubStoreError(RuntimeError):
    pass


class GitHubStore:
    """Stores sharded JSONL files in a private GitHub repository."""

    def __init__(self, token: str, owner: str, repo: str, branch: str, data_dir: str):
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.data_dir = data_dir.strip("/")
        self.base = f"https://api.github.com/repos/{owner}/{repo}"
        self.session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "PUT"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "personal-vault-web/1.0",
            }
        )
        self.shas: dict[str, str] = {}

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.request(method, url, timeout=(10, 45), **kwargs)
        except requests.RequestException as exc:
            raise GitHubStoreError(f"GitHub connection failed: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            message = ""
            try:
                message = str(response.json().get("message", ""))
            except ValueError:
                pass
            raise GitHubStoreError(f"GitHub API returned HTTP {response.status_code}: {message[:180]}")
        return response

    def load_all(self) -> dict[str, list[dict[str, Any]]]:
        ref_url = f"{self.base}/git/ref/heads/{quote(self.branch, safe='/')}"
        ref = self._request("GET", ref_url).json()
        commit_sha = ref["object"]["sha"]
        commit = self._request("GET", f"{self.base}/git/commits/{commit_sha}").json()
        tree_sha = commit["tree"]["sha"]
        tree = self._request("GET", f"{self.base}/git/trees/{tree_sha}", params={"recursive": "1"}).json()
        if tree.get("truncated"):
            raise GitHubStoreError("GitHub repository tree is too large to restore safely in one pass")

        prefix = self.data_dir + "/"
        files: dict[str, list[dict[str, Any]]] = {}
        for item in tree.get("tree", []):
            path = item.get("path", "")
            if item.get("type") != "blob" or not path.startswith(prefix) or not path.endswith(".jsonl"):
                continue
            blob = self._request("GET", f"{self.base}/git/blobs/{item['sha']}").json()
            raw = base64.b64decode(blob.get("content", ""))
            git_blob_header = f"blob {len(raw)}\0".encode("utf-8")
            actual_sha = hashlib.sha1(git_blob_header + raw).hexdigest()
            if actual_sha != item["sha"]:
                raise GitHubStoreError(f"GitHub blob checksum mismatch in {path}")
            records: list[dict[str, Any]] = []
            for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                    if isinstance(value, dict) and value.get("id"):
                        records.append(value)
                except json.JSONDecodeError as exc:
                    raise GitHubStoreError(f"Invalid JSONL data in {path}, line {line_number}") from exc
            files[path] = records
            self.shas[path] = item["sha"]
        return files

    def get_text(self, path: str) -> str | None:
        """Read a small text file from the configured branch. Returns None if absent."""
        encoded_path = quote(path, safe="/")
        try:
            payload = self._request(
                "GET",
                f"{self.base}/contents/{encoded_path}",
                params={"ref": self.branch},
            ).json()
        except GitHubStoreError as exc:
            if "HTTP 404" in str(exc):
                self.shas.pop(path, None)
                return None
            raise
        if not isinstance(payload, dict) or payload.get("type") != "file":
            raise GitHubStoreError(f"GitHub path is not a file: {path}")
        if payload.get("encoding") != "base64":
            raise GitHubStoreError(f"Unsupported GitHub file encoding for {path}")
        try:
            raw = base64.b64decode(payload.get("content", ""), validate=False)
            value = raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubStoreError(f"Could not decode GitHub file: {path}") from exc
        if payload.get("sha"):
            self.shas[path] = str(payload["sha"])
        return value

    def put_file(self, path: str, content: str, commit_message: str) -> str:
        encoded_path = quote(path, safe="/")
        payload: dict[str, Any] = {
            "message": commit_message[:120],
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        existing_sha = self.shas.get(path)
        if existing_sha:
            payload["sha"] = existing_sha
        response = self._request("PUT", f"{self.base}/contents/{encoded_path}", json=payload).json()
        file_info = response.get("content") or {}
        new_sha = file_info.get("sha")
        if not new_sha:
            # Refresh the tree on a rare API response variation rather than
            # pretending the write succeeded without a revision identifier.
            self.shas.pop(path, None)
            self._refresh_single_sha(path)
            new_sha = self.shas.get(path)
        if not new_sha:
            raise GitHubStoreError("GitHub accepted the write but did not return a file SHA")
        raw_content = content.encode("utf-8")
        expected_sha = hashlib.sha1(f"blob {len(raw_content)}\0".encode("utf-8") + raw_content).hexdigest()
        if new_sha != expected_sha:
            raise GitHubStoreError("GitHub file checksum did not match the uploaded content")
        self.shas[path] = new_sha
        return new_sha

    def _refresh_single_sha(self, path: str) -> None:
        encoded_path = quote(path, safe="/")
        response = self._request(
            "GET",
            f"{self.base}/contents/{encoded_path}",
            params={"ref": self.branch},
        ).json()
        if isinstance(response, dict) and response.get("sha"):
            self.shas[path] = response["sha"]
