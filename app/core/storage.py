from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from collections import Counter
from typing import Any

from .github_store import GitHubStore
from .drive_store import GoogleDriveStore
from .parsing import iso_utc, partition_date


log = logging.getLogger(__name__)


def _jsonl(records: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records)


class VaultStorage:
    def __init__(
        self,
        github: GitHubStore | None,
        data_dir: str,
        max_records_per_shard: int = 250,
        drive: GoogleDriveStore | None = None,
    ):
        if github is None and drive is None:
            raise ValueError("At least one persistent storage backend is required")
        self.github = github
        self.data_dir = data_dir.strip("/")
        self.max_records_per_shard = max(10, min(max_records_per_shard, 1000))
        self.drive = drive
        self.shards: dict[str, list[dict[str, Any]]] = {}
        self.record_locations: dict[str, str] = {}
        self.dirty_drive_paths: set[str] = set()
        self._lock = threading.RLock()

    def initialize(self) -> None:
        with self._lock:
            github_files: dict[str, list[dict[str, Any]]] = {}
            drive_files: dict[str, list[dict[str, Any]]] = {}
            drive_load_ok = True

            if self.github:
                # When GitHub is configured it is the primary source in dual mode.
                github_files = self.github.load_all()

            if self.drive:
                try:
                    drive_files = self.drive.load_all()
                except Exception as exc:
                    drive_load_ok = False
                    # Do not start an empty vault when Drive is the only storage,
                    # or when an empty GitHub repo cannot be checked against backup.
                    if not self.github or not github_files:
                        raise RuntimeError(
                            "Google Drive could not be read; refusing to start without verifying existing vault data"
                        ) from exc
                    log.warning(
                        "Google Drive is temporarily unavailable; GitHub data is usable and Drive sync will retry: %s",
                        exc.__class__.__name__,
                    )

            if self.github and self.drive and drive_load_ok and not github_files and drive_files:
                log.info("GitHub vault is empty; restoring its files from Google Drive")
                for path, records in sorted(drive_files.items()):
                    content = _jsonl(records)
                    self.github.put_file(path, content, "Restore vault shard from Google Drive")
                    github_files[path] = records

            # GitHub wins in dual mode. Drive is the primary and only data source
            # when GitHub credentials are not configured.
            if self.github:
                self.shards = github_files
            else:
                self.shards = drive_files
            self._rebuild_index()

            if self.github and self.drive:
                if not drive_load_ok:
                    self.dirty_drive_paths.update(self.shards)
                else:
                    # Reconcile the secondary Drive mirror from GitHub.
                    for path, records in sorted(self.shards.items()):
                        try:
                            self.drive.put_file(path, _jsonl(records))
                            self.dirty_drive_paths.discard(path)
                        except Exception as exc:
                            self.dirty_drive_paths.add(path)
                            log.warning("Drive mirror is pending for %s: %s", path, exc.__class__.__name__)

        log.info("Vault ready: %d records across %d shard files", len(self.record_locations), len(self.shards))

    def _rebuild_index(self) -> None:
        self.record_locations.clear()
        for path, records in self.shards.items():
            for record in records:
                record_id = str(record.get("id", ""))
                if record_id:
                    self.record_locations[record_id] = path

    def _new_shard_path(self, record: dict[str, Any]) -> str:
        date_path = partition_date(record)
        prefix = f"{self.data_dir}/{date_path}/part-"
        paths = sorted(path for path in self.shards if path.startswith(prefix) and path.endswith(".jsonl"))
        if paths:
            last_path = paths[-1]
            if len(self.shards[last_path]) < self.max_records_per_shard:
                return last_path
            part_number = int(last_path.rsplit("part-", 1)[1].split(".", 1)[0]) + 1
        else:
            part_number = 1
        return f"{prefix}{part_number:04d}.jsonl"

    def _commit_shard(self, path: str, records: list[dict[str, Any]], action: str) -> None:
        content = _jsonl(records)
        date_label = path.rsplit("/", 1)[-1]

        # Commit to the configured primary backend before changing in-memory state.
        # In dual mode GitHub is primary; in Drive-only mode Drive is primary.
        if self.github:
            self.github.put_file(path, content, f"Vault {action}: {date_label}")
        elif self.drive:
            self.drive.put_file(path, content)

        self.shards[path] = records
        self._rebuild_index()

        # With both backends configured, mirror only after GitHub has committed.
        # Drive-only mode already wrote to Drive as its primary store.
        if self.github and self.drive:
            pending_paths = sorted(self.dirty_drive_paths | {path})
            for pending_path in pending_paths:
                pending_records = self.shards.get(pending_path)
                if pending_records is None:
                    self.dirty_drive_paths.discard(pending_path)
                    continue
                try:
                    pending_content = content if pending_path == path else _jsonl(pending_records)
                    self.drive.put_file(pending_path, pending_content)
                    self.dirty_drive_paths.discard(pending_path)
                except Exception as exc:
                    self.dirty_drive_paths.add(pending_path)
                    log.warning(
                        "Primary storage is saved; Google Drive mirror pending for %s: %s",
                        pending_path, exc.__class__.__name__,
                    )

    def add_or_update(self, record: dict[str, Any]) -> tuple[str, bool]:
        with self._lock:
            record_id = str(record["id"])
            existing_path = self.record_locations.get(record_id)
            if existing_path:
                records = [dict(item) for item in self.shards[existing_path]]
                for index, old in enumerate(records):
                    if old.get("id") == record_id:
                        incoming_edit = record.get("edited_at")
                        previous_edit = old.get("edited_at")
                        # Ignore an old/original update arriving after a newer edit.
                        if previous_edit and not incoming_edit:
                            return record_id, False
                        if previous_edit and incoming_edit and str(incoming_edit) <= str(previous_edit):
                            return record_id, False
                        content_keys = ("text", "entities", "hashtags", "links", "edited_at")
                        if all(old.get(key) == record.get(key) for key in content_keys):
                            return record_id, False
                        merged = dict(old)
                        deleted_state = bool(old.get("is_deleted", False))
                        deleted_at = old.get("deleted_at")
                        merged.update(record)
                        # An edit event must never silently undelete a record.
                        merged["is_deleted"] = deleted_state
                        merged["deleted_at"] = deleted_at
                        records[index] = merged
                        break
                self._commit_shard(existing_path, records, "update")
                return record_id, False

            path = self._new_shard_path(record)
            records = [dict(item) for item in self.shards.get(path, [])]
            records.append(dict(record))
            self._commit_shard(path, records, "save")
            return record_id, True

    @staticmethod
    def _parse_edit_time(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _merge_imported_edit(
        cls, existing: dict[str, Any], incoming: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Apply only a demonstrably newer Telegram Desktop edit to an existing import."""
        incoming_edit = cls._parse_edit_time(incoming.get("edited_at"))
        existing_edit = cls._parse_edit_time(existing.get("edited_at"))
        if incoming_edit is None or (existing_edit is not None and incoming_edit <= existing_edit):
            return None

        merged = dict(existing)
        was_deleted = bool(existing.get("is_deleted", False))
        deleted_at = existing.get("deleted_at")
        original_created_at = existing.get("created_at")
        merged.update(incoming)
        # Keep the first-seen creation time and local soft-delete state.
        if original_created_at:
            merged["created_at"] = original_created_at
        merged["is_deleted"] = was_deleted
        merged["deleted_at"] = deleted_at
        merged["updated_at"] = incoming.get("updated_at") or incoming.get("edited_at")
        return merged

    def import_records(self, imported: list[dict[str, Any]]) -> tuple[int, int, int]:
        """Merge an export, updating only records with a newer edited_at timestamp.

        Returns (added, updated, skipped). Existing unrelated records and their
        original creation dates are preserved. A repeated/older export is idempotent.
        """
        added = 0
        updated = 0
        skipped = 0
        with self._lock:
            # Each affected shard is committed once, whether it contains additions,
            # edits, or both. This avoids replacing a shard with only the new import.
            pending_by_path: dict[str, list[dict[str, Any]]] = {}
            pending_positions: dict[str, tuple[str, int]] = {}

            for incoming in imported:
                record_id = str(incoming.get("id", ""))
                if not record_id:
                    skipped += 1
                    continue

                # Handle duplicate IDs inside a single JSON file as well as IDs
                # already present in the vault.
                if record_id in pending_positions:
                    path, index = pending_positions[record_id]
                    current = pending_by_path[path][index]
                    merged = self._merge_imported_edit(current, incoming)
                    if merged is None:
                        skipped += 1
                    else:
                        pending_by_path[path][index] = merged
                        updated += 1
                    continue

                existing_path = self.record_locations.get(record_id)
                if existing_path:
                    records = pending_by_path.setdefault(
                        existing_path, [dict(item) for item in self.shards[existing_path]]
                    )
                    index = next(
                        (i for i, item in enumerate(records) if str(item.get("id", "")) == record_id),
                        -1,
                    )
                    if index < 0:
                        skipped += 1
                        continue
                    pending_positions[record_id] = (existing_path, index)
                    merged = self._merge_imported_edit(records[index], incoming)
                    if merged is None:
                        skipped += 1
                    else:
                        records[index] = merged
                        updated += 1
                    continue

                record = dict(incoming)
                date_path = partition_date(record)
                prefix = f"{self.data_dir}/{date_path}/part-"
                candidate_paths = sorted(
                    path for path in set(self.shards) | set(pending_by_path)
                    if path.startswith(prefix) and path.endswith(".jsonl")
                )
                destination = None
                for path in candidate_paths:
                    current_count = len(pending_by_path.get(path, self.shards.get(path, [])))
                    if current_count < self.max_records_per_shard:
                        destination = path
                        break
                if destination is None:
                    next_number = 1
                    if candidate_paths:
                        next_number = max(
                            int(path.rsplit("part-", 1)[1].split(".", 1)[0])
                            for path in candidate_paths
                        ) + 1
                    destination = f"{prefix}{next_number:04d}.jsonl"
                records = pending_by_path.setdefault(
                    destination, [dict(item) for item in self.shards.get(destination, [])]
                )
                pending_positions[record_id] = (destination, len(records))
                records.append(record)
                added += 1

            for path, records in sorted(pending_by_path.items()):
                self._commit_shard(path, records, "import-merge")
        return added, updated, skipped

    def all_records(self, include_deleted: bool = True) -> list[dict[str, Any]]:
        """Return a stable snapshot of every record for web search and export."""
        with self._lock:
            records = [
                dict(record)
                for shard in self.shards.values()
                for record in shard
                if include_deleted or not record.get("is_deleted")
            ]
        records.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return records

    def get(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            path = self.record_locations.get(record_id)
            if not path:
                return None
            for record in self.shards[path]:
                if record.get("id") == record_id:
                    return dict(record)
        return None

    def update_text(self, record_id: str, text: str, entities: list[dict[str, Any]] | None = None) -> bool:
        from .parsing import extract_tags_and_links

        with self._lock:
            path = self.record_locations.get(record_id)
            if not path:
                return False
            records = [dict(item) for item in self.shards[path]]
            for index, record in enumerate(records):
                if record.get("id") == record_id:
                    tags, links = extract_tags_and_links(text, entities or [])
                    record.update(
                        {
                            "text": text,
                            "entities": entities or [],
                            "hashtags": tags,
                            "links": links,
                            "updated_at": iso_utc(),
                            "edited_at": iso_utc(),
                        }
                    )
                    records[index] = record
                    self._commit_shard(path, records, "edit")
                    return True
        return False

    def set_deleted(self, record_id: str, deleted: bool) -> bool:
        with self._lock:
            path = self.record_locations.get(record_id)
            if not path:
                return False
            records = [dict(item) for item in self.shards[path]]
            for index, record in enumerate(records):
                if record.get("id") == record_id:
                    if bool(record.get("is_deleted")) == deleted:
                        return True
                    record["is_deleted"] = deleted
                    record["deleted_at"] = iso_utc() if deleted else None
                    record["updated_at"] = iso_utc()
                    records[index] = record
                    self._commit_shard(path, records, "delete" if deleted else "restore")
                    return True
        return False

    def search(self, query: str, include_deleted: bool = False, limit: int = 10) -> list[dict[str, Any]]:
        needle = query.casefold().strip().lstrip("#")
        if not needle:
            return []
        matches: list[dict[str, Any]] = []
        with self._lock:
            for records in self.shards.values():
                for record in records:
                    if record.get("is_deleted") and not include_deleted:
                        continue
                    haystacks = [
                        str(record.get("text", "")),
                        " ".join(str(tag) for tag in record.get("hashtags", [])),
                        " ".join(str(link) for link in record.get("links", [])),
                    ]
                    if any(needle in item.casefold() for item in haystacks):
                        matches.append(dict(record))
        matches.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return matches[: max(1, min(limit, 50))]

    def by_tag(self, tag: str, limit: int = 10) -> list[dict[str, Any]]:
        needle = tag.casefold().lstrip("#")
        matches = []
        with self._lock:
            for records in self.shards.values():
                for record in records:
                    if not record.get("is_deleted") and needle in record.get("hashtags", []):
                        matches.append(dict(record))
        matches.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return matches[: max(1, min(limit, 50))]

    def by_date(self, date_text: str, limit: int = 10) -> list[dict[str, Any]]:
        matches = []
        with self._lock:
            for records in self.shards.values():
                for record in records:
                    if not record.get("is_deleted") and str(record.get("created_at", "")).startswith(date_text):
                        matches.append(dict(record))
        matches.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return matches[: max(1, min(limit, 50))]

    def recent(self, limit: int = 10, include_deleted: bool = False) -> list[dict[str, Any]]:
        records = []
        with self._lock:
            for shard in self.shards.values():
                records.extend(dict(record) for record in shard if include_deleted or not record.get("is_deleted"))
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return records[: max(1, min(limit, 50))]

    def export_jsonl(self) -> str:
        with self._lock:
            records = []
            for path in sorted(self.shards):
                records.extend(self.shards[path])
            records.sort(key=lambda item: item.get("created_at", ""))
            return _jsonl(records)

    def stats(self) -> dict[str, int | bool | str]:
        with self._lock:
            all_records = [record for shard in self.shards.values() for record in shard]
            counter = Counter(bool(record.get("is_deleted")) for record in all_records)
            return {
                "total": len(all_records),
                "active": counter[False],
                "deleted": counter[True],
                "shards": len(self.shards),
                "github_enabled": self.github is not None,
                "drive_enabled": self.drive is not None,
                "primary_storage": "GitHub" if self.github else "Google Drive",
                "drive_pending": len(self.dirty_drive_paths),
            }

    def backup_now(self) -> tuple[int, int]:
        if not self.drive:
            return 0, 0
        success = 0
        failed = 0
        with self._lock:
            paths = list(self.shards)
            for path in paths:
                try:
                    self.drive.put_file(path, _jsonl(self.shards[path]))
                    self.dirty_drive_paths.discard(path)
                    success += 1
                except Exception as exc:
                    log.warning("Drive backup retry failed for %s: %s", path, exc)
                    self.dirty_drive_paths.add(path)
                    failed += 1
        return success, failed
