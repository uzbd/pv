from app.core.telegram_export import parse_saved_messages_export


def test_parse_saved_messages_json_export():
    payload = {
        "name": "Saved Messages",
        "type": "personal_chat",
        "id": 123,
        "messages": [
            {"id": 1, "type": "message", "date_unixtime": "1700000000", "text": [
                {"type": "bold", "text": "Hello"}, " #Python ",
                {"type": "link", "text": "OpenAI", "href": "https://openai.com"},
            ]},
            {"id": 2, "type": "service", "date": "2023-11-14T00:00:00", "text": "joined"},
            {"id": 3, "type": "message", "date": "2023-11-14T00:00:00", "text": ""},
        ],
    }
    records, skipped = parse_saved_messages_export(payload)
    assert len(records) == 1
    assert skipped == 2
    assert records[0]["text"] == "Hello #Python OpenAI"
    assert records[0]["hashtags"] == ["python"]
    assert records[0]["links"] == ["https://openai.com"]
    assert records[0]["id"].startswith("td_")
    assert records[0]["created_at"] == "2023-11-14T22:13:20Z"


def test_reject_non_saved_messages_export():
    try:
        parse_saved_messages_export({"name": "Some Group", "type": "personal_chat", "messages": []})
    except ValueError as exc:
        assert "Saved Messages" in str(exc)
    else:
        raise AssertionError("expected Saved Messages export validation")


def test_parse_saved_messages_edit_timestamp():
    payload = {
        "name": "Saved Messages",
        "type": "personal_chat",
        "id": 123,
        "messages": [{
            "id": 44,
            "type": "message",
            "date_unixtime": "1700000000",
            "edited_unixtime": "1700003600",
            "text": "Edited note",
        }],
    }
    records, skipped = parse_saved_messages_export(payload)
    assert skipped == 0
    assert records[0]["edited_at"] == "2023-11-14T23:13:20Z"
    assert records[0]["updated_at"] == records[0]["edited_at"]
