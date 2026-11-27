from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.parsing import build_record, extract_tags_and_links, stable_vault_id
from app.core.storage import VaultStorage


class FakeGitHub:
    def __init__(self):
        self.files = {}

    def load_all(self):
        return {path: [dict(record) for record in records] for path, records in self.files.items()}

    def put_file(self, path, content, commit_message):
        self.files[path] = [json.loads(line) for line in content.splitlines() if line.strip()]
        return "fake-sha"


class FakeDrive:
    def __init__(self):
        self.files = {}

    def load_all(self):
        return {path: [dict(record) for record in records] for path, records in self.files.items()}

    def put_file(self, path, content):
        self.files[path] = [json.loads(line) for line in content.splitlines() if line.strip()]


def make_record(message_id: int, text: str, chat_id: int = 10001):
    message = SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        message_id=message_id,
        date=datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc),
        edit_date=None,
        text=text,
        entities=[],
    )
    return build_record(message)


def test_stable_id_and_extractors():
    assert stable_vault_id(100, 20) == stable_vault_id(100, 20)
    assert stable_vault_id(100, 20) != stable_vault_id(100, 21)
    tags, links = extract_tags_and_links("Read #GitHub and #বাংলা: https://example.com/page.")
    assert tags == ["github", "বাংলা"]
    assert links == ["https://example.com/page"]


def test_save_edit_search_soft_delete_and_restore():
    github = FakeGitHub()
    drive = FakeDrive()
    store = VaultStorage(github, "vault-data", max_records_per_shard=10, drive=drive)
    store.initialize()

    record = make_record(1, "First note about #GitHub")
    record_id, created = store.add_or_update(record)
    assert created is True
    assert store.get(record_id)["text"] == "First note about #GitHub"
    assert drive.files, "The Drive mirror should receive the committed shard"

    assert store.update_text(record_id, "Updated note with https://example.com") is True
    assert store.search("example.com")[0]["id"] == record_id

    assert store.set_deleted(record_id, True) is True
    assert store.search("example.com") == []
    assert store.get(record_id)["is_deleted"] is True

    assert store.set_deleted(record_id, False) is True
    assert store.search("example.com")[0]["id"] == record_id
    stats = store.stats()
    assert stats["active"] == 1
    assert stats["deleted"] == 0


def test_edited_telegram_record_does_not_undelete():
    store = VaultStorage(FakeGitHub(), "vault-data")
    store.initialize()
    first = make_record(3, "Original text")
    record_id, _ = store.add_or_update(first)
    store.set_deleted(record_id, True)

    edited = make_record(3, "Edited original text")
    store.add_or_update(edited)
    result = store.get(record_id)
    assert result["text"] == "Edited original text"
    assert result["is_deleted"] is True


def test_date_search_uses_utc_created_date():
    store = VaultStorage(FakeGitHub(), "vault-data")
    store.initialize()
    record = make_record(9, "A note for the selected date")
    store.add_or_update(record)
    assert len(store.by_date("2026-11-27")) == 1
    assert store.by_date("2026-11-28") == []


def test_bulk_import_is_idempotent_and_splits_shards():
    store = VaultStorage(FakeGitHub(), "vault-data", max_records_per_shard=10)
    store.initialize()
    records = []
    for index in range(23):
        records.append({
            "id": f"td_{index}",
            "created_at": "2026-11-27T10:30:00Z",
            "updated_at": "2026-11-27T10:30:00Z",
            "text": f"Imported note {index}",
            "entities": [], "hashtags": [], "links": [],
            "is_deleted": False, "deleted_at": None, "schema_version": 1,
        })
    imported, updated, skipped = store.import_records(records)
    assert (imported, updated, skipped) == (23, 0, 0)
    assert store.stats()["total"] == 23
    imported_again, updated_again, skipped_again = store.import_records(records)
    assert (imported_again, updated_again, skipped_again) == (0, 0, 23)
    assert store.stats()["total"] == 23
    assert len(store.shards) == 3


def test_import_updates_newer_telegram_edit_and_preserves_other_records():
    store = VaultStorage(FakeGitHub(), "vault-data", max_records_per_shard=10)
    store.initialize()
    original = {
        "id": "td_chat1_msg1", "created_at": "2023-11-14T10:00:00Z",
        "updated_at": "2023-11-14T10:00:00Z", "edited_at": None,
        "text": "Original text", "entities": [], "hashtags": [], "links": [],
        "is_deleted": False, "deleted_at": None, "schema_version": 1,
        "telegram_export_chat_id": "chat1", "telegram_export_message_id": "1",
    }
    unrelated = dict(original, id="td_chat1_msg2", telegram_export_message_id="2", text="Keep this note")
    assert store.import_records([original, unrelated]) == (2, 0, 0)

    edited = dict(original, updated_at="2023-11-15T10:00:00Z", edited_at="2023-11-15T10:00:00Z", text="Edited text #Updated", hashtags=["updated"])
    assert store.import_records([edited]) == (0, 1, 0)
    assert store.get(original["id"])["text"] == "Edited text #Updated"
    assert store.get(original["id"])["created_at"] == original["created_at"]
    assert store.get(unrelated["id"])["text"] == "Keep this note"
    assert store.stats()["total"] == 2

    # Importing the same edited export again is idempotent.
    assert store.import_records([edited]) == (0, 0, 1)


def test_import_does_not_overwrite_newer_local_edit_or_undelete_record():
    store = VaultStorage(FakeGitHub(), "vault-data")
    store.initialize()
    original = {
        "id": "td_chat2_msg1", "created_at": "2023-11-14T10:00:00Z",
        "updated_at": "2023-11-14T10:00:00Z", "edited_at": None,
        "text": "Original", "entities": [], "hashtags": [], "links": [],
        "is_deleted": False, "deleted_at": None, "schema_version": 1,
    }
    store.import_records([original])
    newer = dict(original, text="Newer local content", edited_at="2023-11-17T10:00:00Z", updated_at="2023-11-17T10:00:00Z")
    store.import_records([newer])
    store.set_deleted(original["id"], True)

    stale_export = dict(original, text="Stale export content", edited_at="2023-11-16T10:00:00Z", updated_at="2023-11-16T10:00:00Z")
    assert store.import_records([stale_export]) == (0, 0, 1)
    result = store.get(original["id"])
    assert result["text"] == "Newer local content"
    assert result["is_deleted"] is True


def test_drive_only_mode_saves_updates_and_restores_without_github():
    drive = FakeDrive()
    store = VaultStorage(None, "vault-data", max_records_per_shard=10, drive=drive)
    store.initialize()

    record = make_record(71, "Saved in Drive only")
    record_id, created = store.add_or_update(record)
    assert created is True
    assert drive.files
    assert store.get(record_id)["text"] == "Saved in Drive only"

    # A new process with only the Drive backend restores the complete vault.
    restarted = VaultStorage(None, "vault-data", max_records_per_shard=10, drive=drive)
    restarted.initialize()
    assert restarted.get(record_id)["text"] == "Saved in Drive only"
    assert restarted.update_text(record_id, "Edited in Drive only") is True
    assert restarted.get(record_id)["text"] == "Edited in Drive only"


def test_drive_only_import_merge_and_duplicate_protection():
    drive = FakeDrive()
    store = VaultStorage(None, "vault-data", max_records_per_shard=10, drive=drive)
    store.initialize()
    imported = [{
        "id": "drive_import_1", "created_at": "2026-11-27T10:00:00Z",
        "updated_at": "2026-11-27T10:00:00Z", "edited_at": None,
        "text": "Drive import", "entities": [], "hashtags": [], "links": [],
        "is_deleted": False, "deleted_at": None, "schema_version": 1,
    }]
    assert store.import_records(imported) == (1, 0, 0)
    assert store.import_records(imported) == (0, 0, 1)
    assert store.stats()["total"] == 1
    assert store.stats()["primary_storage"] == "Google Drive"


def test_drive_only_storage_failure_does_not_mutate_memory():
    class BrokenDrive(FakeDrive):
        def put_file(self, path, content):
            raise RuntimeError("drive unavailable")

    drive = BrokenDrive()
    store = VaultStorage(None, "vault-data", drive=drive)
    store.initialize()
    record = make_record(72, "Must not be marked saved")
    try:
        store.add_or_update(record)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Drive write failure must be propagated")
    assert store.stats()["total"] == 0


def test_drive_only_startup_fails_if_existing_data_cannot_be_read():
    class BrokenReadDrive(FakeDrive):
        def load_all(self):
            raise RuntimeError("drive read failed")

    store = VaultStorage(None, "vault-data", drive=BrokenReadDrive())
    try:
        store.initialize()
    except RuntimeError as exc:
        assert "refusing to start" in str(exc)
    else:
        raise AssertionError("Drive-only startup must fail when backup cannot be read")


def test_dual_mode_restores_drive_data_into_empty_github():
    drive = FakeDrive()
    seed = VaultStorage(None, "vault-data", drive=drive)
    seed.initialize()
    record = make_record(73, "Restore this Drive record")
    seed.add_or_update(record)

    github = FakeGitHub()
    recovered = VaultStorage(github, "vault-data", drive=drive)
    recovered.initialize()

    assert recovered.get(record["id"])["text"] == "Restore this Drive record"
    assert github.files, "Drive-only data should be restored into the configured GitHub repository"


def test_dual_mode_keeps_github_as_primary_when_drive_has_stale_data():
    github = FakeGitHub()
    drive = FakeDrive()
    github_store = VaultStorage(github, "vault-data")
    github_store.initialize()
    authoritative = make_record(74, "GitHub is authoritative")
    github_store.add_or_update(authoritative)

    stale = make_record(75, "Stale Drive-only extra")
    seed_drive = VaultStorage(None, "vault-data", drive=drive)
    seed_drive.initialize()
    seed_drive.add_or_update(stale)

    dual = VaultStorage(github, "vault-data", drive=drive)
    dual.initialize()
    assert dual.get(authoritative["id"])["text"] == "GitHub is authoritative"
    assert dual.get(stale["id"]) is None
    assert drive.files and authoritative["id"] in {r["id"] for rows in drive.files.values() for r in rows}
