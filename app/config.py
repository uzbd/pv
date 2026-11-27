from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


# A platform-generated SECRET_KEY is preferred. If a host does not provide one,
# this process-local key keeps the app deployable with only storage credentials;
# browser sessions will need to sign in again after a restart.
def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


RUNTIME_SESSION_SECRET = _env("SECRET_KEY") or secrets.token_urlsafe(48)


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    return max(minimum, min(value, maximum))


def _bool_env(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_password: str
    secret_key: str
    app_title: str
    github_token: str
    github_owner: str
    github_repo: str
    setup_key: str
    github_branch: str
    data_dir: str
    google_client_b64: str
    google_token_b64: str
    google_drive_folder_id: str
    port: int
    max_records_per_shard: int
    max_upload_mb: int
    session_max_age: int
    cookie_secure: bool
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        app_password = _env("APP_PASSWORD")
        if app_password and len(app_password) < 16:
            raise ConfigError("APP_PASSWORD must contain at least 16 characters")
        if len(app_password) > 1024:
            raise ConfigError("APP_PASSWORD must not exceed 1024 characters")
        secret_key = _env("SECRET_KEY") or RUNTIME_SESSION_SECRET
        if len(secret_key) < 32:
            raise ConfigError("SECRET_KEY must contain at least 32 characters")

        github_token = _env("GITHUB_TOKEN")
        github_owner = _env("GITHUB_OWNER")
        github_repo = _env("GITHUB_REPO")
        setup_key = _env("VAULT_SETUP_KEY")
        if setup_key and len(setup_key) < 32:
            raise ConfigError("VAULT_SETUP_KEY must contain at least 32 characters when configured")
        github_values = (github_token, github_owner, github_repo)
        if any(github_values) and not all(github_values):
            raise ConfigError(
                "GitHub storage is partially configured. Set GITHUB_TOKEN, GITHUB_OWNER, "
                "and GITHUB_REPO together, or leave all three blank."
            )

        google_client_b64 = _env("GOOGLE_OAUTH_CLIENT_B64")
        google_token_b64 = _env("GOOGLE_OAUTH_TOKEN_B64")
        google_drive_folder_id = _env("GOOGLE_DRIVE_FOLDER_ID")
        drive_values = (google_client_b64, google_token_b64)
        if any(drive_values) and not all(drive_values):
            raise ConfigError(
                "Google Drive storage is partially configured. Set GOOGLE_OAUTH_CLIENT_B64 "
                "and GOOGLE_OAUTH_TOKEN_B64 together, or leave both blank."
            )
        if google_drive_folder_id and not all(drive_values):
            raise ConfigError("GOOGLE_DRIVE_FOLDER_ID requires both Google Drive OAuth credentials")

        github_enabled = all(github_values)
        drive_enabled = all(drive_values)
        if not github_enabled and not drive_enabled:
            raise ConfigError(
                "Configure at least one persistent storage backend: GitHub, Google Drive, or both."
            )
        if not app_password and not github_enabled:
            raise ConfigError(
                "For first-run password setup, configure GitHub storage. Drive-only deployments must set APP_PASSWORD."
            )

        data_dir = (_env("VAULT_DATA_DIR") or _env("GITHUB_DATA_DIR") or "vault-data").strip("/")
        if not data_dir or ".." in data_dir.split("/"):
            raise ConfigError("VAULT_DATA_DIR must be a safe relative storage path")

        is_production = _env("APP_ENV", "production").casefold() == "production"
        return cls(
            app_password=app_password,
            secret_key=secret_key,
            app_title=_env("APP_TITLE", "Personal Vault") or "Personal Vault",
            github_token=github_token,
            github_owner=github_owner,
            github_repo=github_repo,
            setup_key=setup_key,
            github_branch=_env("GITHUB_BRANCH", "main") or "main",
            data_dir=data_dir,
            google_client_b64=google_client_b64,
            google_token_b64=google_token_b64,
            google_drive_folder_id=google_drive_folder_id,
            port=_int_env("PORT", 8000, 1, 65535),
            max_records_per_shard=_int_env("MAX_RECORDS_PER_SHARD", 250, 10, 1000),
            max_upload_mb=_int_env("MAX_UPLOAD_MB", 25, 1, 100),
            session_max_age=_int_env("SESSION_MAX_AGE", 86400, 600, 2592000),
            cookie_secure=_bool_env("COOKIE_SECURE", is_production),
            log_level=_env("LOG_LEVEL", "INFO").upper() or "INFO",
        )

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_token and self.github_owner and self.github_repo)

    @property
    def drive_enabled(self) -> bool:
        return bool(self.google_client_b64 and self.google_token_b64)

    @property
    def primary_storage_name(self) -> str:
        return "GitHub" if self.github_enabled else "Google Drive"

    @property
    def storage_mode(self) -> str:
        if self.github_enabled and self.drive_enabled:
            return "GitHub + Google Drive"
        return "GitHub only" if self.github_enabled else "Google Drive only"
