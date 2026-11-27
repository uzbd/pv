import re

from fastapi.testclient import TestClient

from app import main
from app.core.storage import VaultStorage


class FakeGitHub:
    def __init__(self):
        self.files = {}
        self.text_files = {}

    def load_all(self):
        return {path: [dict(item) for item in rows] for path, rows in self.files.items()}

    def get_text(self, path):
        return self.text_files.get(path)

    def put_file(self, path, content, commit_message):
        import json
        if path.endswith(".jsonl"):
            self.files[path] = [json.loads(line) for line in content.splitlines() if line.strip()]
        else:
            self.text_files[path] = content
        return "fake-sha"


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "Expected a CSRF token in the HTML form"
    return match.group(1)


def test_login_dashboard_and_create_message(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "a-strong-test-password")
    monkeypatch.setenv("SECRET_KEY", "test-only-secret-key-with-more-than-32-characters")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("GITHUB_OWNER", "example")
    monkeypatch.setenv("GITHUB_REPO", "vault")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_B64", "")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_B64", "")
    monkeypatch.setenv("COOKIE_SECURE", "false")

    fake_storage = VaultStorage(FakeGitHub(), "vault-data")
    fake_storage.initialize()
    monkeypatch.setattr(main, "create_storage", lambda settings: fake_storage)

    with TestClient(main.app) as client:
        blocked = client.get("/", follow_redirects=False)
        assert blocked.status_code == 303
        assert blocked.headers["location"] == "/login"

        login_page = client.get("/login")
        assert login_page.status_code == 200
        csrf = csrf_from(login_page.text)
        login_result = client.post(
            "/login",
            data={"password": "a-strong-test-password", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert login_result.status_code == 303
        assert login_result.headers["location"] == "/"

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Overview" in dashboard.text
        csrf = csrf_from(dashboard.text)

        saved = client.post(
            "/messages/new",
            data={"text": "A web note about #GitHub https://example.com", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert fake_storage.stats()["total"] == 1
        record = fake_storage.recent(1)[0]
        assert record["hashtags"] == ["github"]
        assert record["links"] == ["https://example.com"]

        message_page = client.get("/messages")
        assert "A web note about" in message_page.text
        assert "github" in message_page.text
        assert client.get(f"/messages/{record['id']}").status_code == 200
        assert client.get(f"/messages/{record['id']}/edit").status_code == 200

        settings_page = client.get("/settings")
        assert settings_page.status_code == 200
        assert "Command directory" not in settings_page.text
        assert "Import messages" in settings_page.text
        csrf = csrf_from(settings_page.text)
        telegram_export = {
            "name": "Saved Messages", "type": "personal_chat", "id": 12345,
            "messages": [{"id": 7, "type": "message", "date_unixtime": "1700000000", "text": "Imported from Telegram #Archive"}],
        }
        imported = client.post(
            "/settings/import",
            data={"csrf_token": csrf},
            files={"file": ("result.json", __import__("json").dumps(telegram_export).encode(), "application/json")},
            follow_redirects=False,
        )
        assert imported.status_code == 303
        assert fake_storage.stats()["total"] == 2
        imported_record = next(item for item in fake_storage.all_records() if item.get("telegram_export_message_id") == "7")
        assert imported_record["text"] == "Imported from Telegram #Archive"

        # A later Telegram Desktop edit updates the matching record, not a second copy.
        edited_export = {
            "name": "Saved Messages", "type": "personal_chat", "id": 12345,
            "messages": [{"id": 7, "type": "message", "date_unixtime": "1700000000", "edited_unixtime": "1700003600", "text": "Edited Telegram archive #Archive"}],
        }
        settings_page = client.get("/settings")
        csrf = csrf_from(settings_page.text)
        client.post(
            "/settings/import",
            data={"csrf_token": csrf},
            files={"file": ("edited.json", __import__("json").dumps(edited_export).encode(), "application/json")},
            follow_redirects=False,
        )
        assert fake_storage.stats()["total"] == 2
        assert fake_storage.get(imported_record["id"])["text"] == "Edited Telegram archive #Archive"

        export = client.get("/settings/export.jsonl")
        assert export.status_code == 200
        assert b"A web note about" in export.content
        assert export.headers["content-disposition"].endswith('personal-vault-export.jsonl"')

        # Protected tools redirect if the browser session is removed.
        client.post("/logout", data={"csrf_token": csrf})
        after_logout = client.get("/settings", follow_redirects=False)
        assert after_logout.status_code == 303
