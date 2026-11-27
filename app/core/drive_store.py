from __future__ import annotations

import base64
import io
import logging
import hashlib
from typing import Any


log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleDriveStoreError(RuntimeError):
    pass


class GoogleDriveStore:
    """Mirrors the same JSONL shards into a visible Google Drive folder."""

    def __init__(self, client_b64: str, token_b64: str, folder_id: str = ""):
        try:
            client_json = base64.b64decode(client_b64).decode("utf-8")
            token_json = base64.b64decode(token_b64).decode("utf-8")
            # The client JSON is decoded and parsed here to fail early if a
            # malformed secret was pasted into the hosting environment.
            import json
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            json.loads(client_json)
            credentials = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
            self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        except Exception as exc:
            raise GoogleDriveStoreError(f"Google Drive credentials could not be loaded: {exc.__class__.__name__}") from exc
        self.folder_id = folder_id.strip()
        self.file_ids: dict[str, str] = {}

    def _ensure_folder(self) -> str:
        if self.folder_id:
            return self.folder_id
        try:
            result = self.service.files().list(
                q="name = 'Telegram Personal Vault' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                spaces="drive",
                pageSize=100,
                fields="files(id,name)",
            ).execute()
            folders = result.get("files", [])
            if folders:
                self.folder_id = folders[0]["id"]
                return self.folder_id
            created = self.service.files().create(
                body={"name": "Telegram Personal Vault", "mimeType": FOLDER_MIME},
                fields="id",
            ).execute()
            self.folder_id = created["id"]
            return self.folder_id
        except Exception as exc:
            raise GoogleDriveStoreError(f"Google Drive folder could not be opened: {exc.__class__.__name__}") from exc

    def load_all(self) -> dict[str, list[dict[str, Any]]]:
        folder_id = self._ensure_folder()
        files: dict[str, list[dict[str, Any]]] = {}
        page_token = None
        try:
            while True:
                result = self.service.files().list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    spaces="drive",
                    pageSize=1000,
                    pageToken=page_token,
                    fields="nextPageToken,files(id,name,appProperties,mimeType)",
                ).execute()
                for item in result.get("files", []):
                    path = (item.get("appProperties") or {}).get("vaultPath")
                    if not path or not path.endswith(".jsonl"):
                        continue
                    from googleapiclient.http import MediaIoBaseDownload

                    request = self.service.files().get(fileId=item["id"], alt="media")
                    buffer = io.BytesIO()
                    downloader = MediaIoBaseDownload(buffer, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                    raw_content = buffer.getvalue()
                    expected_checksum = (item.get("appProperties") or {}).get("sha256")
                    actual_checksum = hashlib.sha256(raw_content).hexdigest()
                    if expected_checksum and expected_checksum != actual_checksum:
                        raise GoogleDriveStoreError(f"Backup checksum mismatch in {path}")
                    content = raw_content.decode("utf-8")
                    records: list[dict[str, Any]] = []
                    import json

                    for line_number, line in enumerate(content.splitlines(), start=1):
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                            if isinstance(record, dict) and record.get("id"):
                                records.append(record)
                        except json.JSONDecodeError as exc:
                            raise GoogleDriveStoreError(f"Invalid backup data in {path}, line {line_number}") from exc
                    files[path] = records
                    self.file_ids[path] = item["id"]
                page_token = result.get("nextPageToken")
                if not page_token:
                    break
            return files
        except GoogleDriveStoreError:
            raise
        except Exception as exc:
            raise GoogleDriveStoreError(f"Google Drive restore failed: {exc.__class__.__name__}") from exc

    def put_file(self, path: str, content: str) -> None:
        folder_id = self._ensure_folder()
        try:
            from googleapiclient.http import MediaIoBaseUpload

            raw_content = content.encode("utf-8")
            checksum = hashlib.sha256(raw_content).hexdigest()
            media = MediaIoBaseUpload(
                io.BytesIO(raw_content),
                mimetype="application/x-ndjson",
                resumable=False,
            )
            metadata = {
                "name": path.rsplit("/", 1)[-1],
                "appProperties": {"vaultPath": path, "sha256": checksum},
            }
            existing_id = self.file_ids.get(path)
            if not existing_id:
                # A previous Drive listing may have failed while GitHub remained
                # available. Look up by the stable vaultPath before creating so a
                # later mirror retry cannot create duplicate Drive files.
                safe_path = path.replace("\\", "\\\\").replace("'", "\\'")
                lookup = self.service.files().list(
                    q=(
                        f"'{folder_id}' in parents and "
                        f"appProperties has {{ key='vaultPath' and value='{safe_path}' }} "
                        "and trashed = false"
                    ),
                    spaces="drive",
                    pageSize=10,
                    fields="files(id)",
                ).execute()
                matches = lookup.get("files", [])
                if matches:
                    existing_id = matches[0]["id"]
                    self.file_ids[path] = existing_id

            if existing_id:
                self.service.files().update(
                    fileId=existing_id,
                    body=metadata,
                    media_body=media,
                    fields="id",
                ).execute()
            else:
                metadata["parents"] = [folder_id]
                result = self.service.files().create(
                    body=metadata,
                    media_body=media,
                    fields="id",
                ).execute()
                self.file_ids[path] = result["id"]
        except Exception as exc:
            raise GoogleDriveStoreError(f"Google Drive backup failed for {path}: {exc.__class__.__name__}") from exc
