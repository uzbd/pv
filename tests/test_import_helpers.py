import json

from app.main import _normalise_import_records, _parse_upload


def test_normalise_records_rebuilds_tags_and_links():
    rows, skipped = _normalise_import_records([{
        "id": "test-1",
        "text": "Read #GitHub https://example.com/path",
        "hashtags": [],
        "links": [],
    }])
    assert skipped == 0
    assert rows[0]["hashtags"] == ["github"]
    assert rows[0]["links"] == ["https://example.com/path"]


def test_parse_native_jsonl():
    raw = (json.dumps({"id": "r1", "text": "A saved note", "created_at": "2026-11-27T00:00:00Z"}) + "\n").encode()
    records, ignored, source = _parse_upload("backup.jsonl", raw)
    assert len(records) == 1
    assert ignored == 0
    assert source == "Vault JSONL"


def test_parse_vault_json_archive():
    raw = json.dumps({"format": "personal-vault-json-export", "records": [
        {"id": "r2", "text": "JSON archive note"}
    ]}).encode()
    records, ignored, source = _parse_upload("backup.json", raw)
    assert records[0]["id"] == "r2"
    assert ignored == 0
    assert source == "Vault JSON"


def test_invalid_file_extension_rejected():
    try:
        _parse_upload("backup.txt", b"hello")
    except ValueError as exc:
        assert ".json" in str(exc)
    else:
        raise AssertionError("Unsupported extensions must fail")


def test_normalise_records_rejects_unsafe_ids():
    rows, skipped = _normalise_import_records([{"id": "../outside", "text": "Unsafe path-like ID"}])
    assert rows == []
    assert skipped == 1
