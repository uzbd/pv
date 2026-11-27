import pytest

from app.config import ConfigError, Settings


def base_env(monkeypatch):
    values = {
        "APP_PASSWORD": "correct-horse-battery-staple",
        "SECRET_KEY": "x" * 48,
        "GITHUB_TOKEN": "ghp_test",
        "GITHUB_OWNER": "example",
        "GITHUB_REPO": "vault",
        "VAULT_SETUP_KEY": "vault-one-time-setup-key-0123456789",
        "GITHUB_BRANCH": "main",
        "GOOGLE_OAUTH_CLIENT_B64": "",
        "GOOGLE_OAUTH_TOKEN_B64": "",
        "GOOGLE_DRIVE_FOLDER_ID": "",
        "VAULT_DATA_DIR": "vault-data",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_github_only_mode(monkeypatch):
    base_env(monkeypatch)
    config = Settings.from_env()
    assert config.github_enabled is True
    assert config.drive_enabled is False
    assert config.primary_storage_name == "GitHub"


def test_drive_only_mode(monkeypatch):
    base_env(monkeypatch)
    for key in ("GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_B64", "client")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_B64", "token")
    config = Settings.from_env()
    assert config.github_enabled is False
    assert config.drive_enabled is True
    assert config.primary_storage_name == "Google Drive"


def test_both_storage_mode(monkeypatch):
    base_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_B64", "client")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_B64", "token")
    config = Settings.from_env()
    assert config.storage_mode == "GitHub + Google Drive"


def test_partial_storage_configuration_fails(monkeypatch):
    base_env(monkeypatch)
    monkeypatch.setenv("GITHUB_REPO", "")
    with pytest.raises(ConfigError, match="partially configured"):
        Settings.from_env()


def test_no_storage_configuration_fails(monkeypatch):
    base_env(monkeypatch)
    for key in ("GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"):
        monkeypatch.setenv(key, "")
    with pytest.raises(ConfigError, match="at least one"):
        Settings.from_env()


def test_short_secret_fails(monkeypatch):
    base_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(ConfigError, match="32 characters"):
        Settings.from_env()


def test_github_only_does_not_require_app_password(monkeypatch):
    base_env(monkeypatch)
    monkeypatch.setenv("APP_PASSWORD", "")
    config = Settings.from_env()
    assert config.github_enabled is True
    assert config.app_password == ""


def test_short_setup_key_fails(monkeypatch):
    base_env(monkeypatch)
    monkeypatch.setenv("VAULT_SETUP_KEY", "too-short")
    with pytest.raises(ConfigError, match="VAULT_SETUP_KEY must contain at least 32 characters"):
        Settings.from_env()
