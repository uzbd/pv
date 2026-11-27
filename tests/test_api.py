import json

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
        if path.endswith(".jsonl"):
            self.files[path] = [json.loads(line) for line in content.splitlines() if line.strip()]
        else:
            self.text_files[path] = content
        return "fake-sha"


def setup_client(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "a-strong-test-password")
    monkeypatch.setenv("SECRET_KEY", "test-only-secret-key-with-more-than-32-characters")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("GITHUB_OWNER", "example")
    monkeypatch.setenv("GITHUB_REPO", "vault")
    monkeypatch.setenv("VAULT_SETUP_KEY", "vault-one-time-setup-key-0123456789")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_B64", "")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_B64", "")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    fake_storage = VaultStorage(FakeGitHub(), "vault-data")
    fake_storage.initialize()
    monkeypatch.setattr(main, "create_storage", lambda settings: fake_storage)
    return TestClient(main.app), fake_storage


def test_api_auth_crud_search_and_export(monkeypatch):
    client, storage = setup_client(monkeypatch)
    with client:
        session = client.get("/api/auth/session")
        assert session.status_code == 200
        csrf = session.json()["csrf_token"]
        assert client.get("/api/dashboard").status_code == 401
        assert client.get("/api/settings/export.json").status_code == 401
        assert client.get("/api/settings").status_code == 401

        login = client.post("/api/auth/login", json={"password": "a-strong-test-password", "csrf_token": csrf})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        cookie_header = client.cookies.get("personal_vault_session")
        assert cookie_header
        set_cookie = client.cookies
        headers = {"X-CSRF-Token": csrf}

        created = client.post("/api/messages", json={"text": "React UI note #Productivity https://example.com"}, headers=headers)
        assert created.status_code == 200
        record = created.json()["record"]
        assert record["hashtags"] == ["productivity"]
        assert record["links"] == ["https://example.com"]

        search = client.get("/api/messages", params={"q": "productivity"})
        assert search.status_code == 200
        assert search.json()["total"] == 1

        edited = client.patch(f"/api/messages/{record['id']}", json={"text": "Updated React note #Design"}, headers=headers)
        assert edited.status_code == 200
        assert edited.json()["record"]["text"] == "Updated React note #Design"

        removed = client.delete(f"/api/messages/{record['id']}", headers=headers)
        assert removed.status_code == 200
        assert storage.stats()["deleted"] == 1
        restored = client.post(f"/api/messages/{record['id']}/restore", headers=headers)
        assert restored.status_code == 200
        assert storage.stats()["active"] == 1

        export = client.get("/api/settings/export.json")
        assert export.status_code == 200
        assert export.json()["records"][0]["text"] == "Updated React note #Design"

        replayable_cookie = client.cookies.get("personal_vault_session")
        logout = client.post("/api/auth/logout", headers=headers)
        assert logout.status_code == 200
        assert client.get("/api/dashboard").status_code == 401
        # Even replaying the previously signed cookie fails because the server
        # has revoked its session ID from the active-session allowlist.
        client.cookies.set("personal_vault_session", replayable_cookie)
        assert client.get("/api/dashboard").status_code == 401


def test_api_telegram_import_and_updated_edit_merge(monkeypatch):
    client, storage = setup_client(monkeypatch)
    with client:
        csrf = client.get("/api/auth/session").json()["csrf_token"]
        login = client.post("/api/auth/login", json={"password": "a-strong-test-password", "csrf_token": csrf})
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        first = {"name": "Saved Messages", "type": "personal_chat", "id": 123, "messages": [{"id": 9, "type": "message", "date_unixtime": "1700000000", "text": "Original note #Archive"}]}
        imported = client.post("/api/settings/import", headers=headers, files={"file": ("result.json", json.dumps(first).encode(), "application/json")})
        assert imported.status_code == 200
        assert imported.json()["added"] == 1
        edited_export = {"name": "Saved Messages", "type": "personal_chat", "id": 123, "messages": [{"id": 9, "type": "message", "date_unixtime": "1700000000", "edited_unixtime": "1700003600", "text": "Edited note #Archive"}]}
        second = client.post("/api/settings/import", headers=headers, files={"file": ("edited.json", json.dumps(edited_export).encode(), "application/json")})
        assert second.status_code == 200
        assert second.json()["updated"] == 1
        assert storage.stats()["total"] == 1
        assert storage.all_records()[0]["text"] == "Edited note #Archive"


def test_first_run_password_setup_is_persisted_in_private_repo(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")
    monkeypatch.setenv("SECRET_KEY", "test-only-secret-key-with-more-than-32-characters")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("GITHUB_OWNER", "example")
    monkeypatch.setenv("GITHUB_REPO", "vault")
    monkeypatch.setenv("VAULT_SETUP_KEY", "vault-one-time-setup-key-0123456789")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_B64", "")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_B64", "")
    monkeypatch.setenv("COOKIE_SECURE", "false")

    github = FakeGitHub()
    fake_storage = VaultStorage(github, "vault-data")
    fake_storage.initialize()
    monkeypatch.setattr(main, "create_storage", lambda settings: fake_storage)

    with TestClient(main.app) as client:
        session = client.get("/api/auth/session").json()
        assert session["setup_required"] is True
        headers = {"X-CSRF-Token": session["csrf_token"]}
        # First-visitor takeover is blocked without the separate setup key.
        too_short = client.post(
            "/api/auth/setup",
            json={"password": "short", "confirm_password": "short", "setup_key": "vault-one-time-setup-key-0123456789"},
            headers=headers,
        )
        assert too_short.status_code == 422
        wrong_owner = client.post(
            "/api/auth/setup",
            json={"password": "this-is-a-long-private-password", "confirm_password": "this-is-a-long-private-password", "setup_key": "wrong-key"},
            headers=headers,
        )
        assert wrong_owner.status_code == 401
        setup = client.post(
            "/api/auth/setup",
            json={"password": "this-is-a-long-private-password", "confirm_password": "this-is-a-long-private-password", "setup_key": "vault-one-time-setup-key-0123456789"},
            headers=headers,
        )
        assert setup.status_code == 200
        assert client.get("/api/dashboard").status_code == 200
        assert ".personal-vault-web/auth.json" in github.text_files
        saved = json.loads(github.text_files[".personal-vault-web/auth.json"])
        assert "digest" in saved and "salt" in saved
        assert "fake-token" not in github.text_files[".personal-vault-web/auth.json"]
        assert "vault-one-time-setup-key" not in github.text_files[".personal-vault-web/auth.json"]
        assert "this-is-a-long-private-password" not in github.text_files[".personal-vault-web/auth.json"]
        assert client.get("/api/dashboard").status_code == 200

    # A fresh application session loads the saved verifier and no longer needs APP_PASSWORD.
    with TestClient(main.app) as client:
        session = client.get("/api/auth/session").json()
        assert session["setup_required"] is False
        headers = {"X-CSRF-Token": session["csrf_token"]}
        rejected = client.post("/api/auth/login", json={"password": "incorrect-password"}, headers=headers)
        assert rejected.status_code == 401
        accepted = client.post("/api/auth/login", json={"password": "this-is-a-long-private-password"}, headers=headers)
        assert accepted.status_code == 200
        csrf = accepted.json()["csrf_token"]
        changed = client.post(
            "/api/auth/password",
            json={
                "current_password": "this-is-a-long-private-password",
                "new_password": "another-very-long-private-password",
                "confirm_password": "another-very-long-private-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert changed.status_code == 200

    with TestClient(main.app) as client:
        session = client.get("/api/auth/session").json()
        headers = {"X-CSRF-Token": session["csrf_token"]}
        old_password = client.post("/api/auth/login", json={"password": "this-is-a-long-private-password"}, headers=headers)
        assert old_password.status_code == 401
        new_password = client.post("/api/auth/login", json={"password": "another-very-long-private-password"}, headers=headers)
        assert new_password.status_code == 200
