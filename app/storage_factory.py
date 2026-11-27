from __future__ import annotations

from .config import Settings
from .core.drive_store import GoogleDriveStore
from .core.github_store import GitHubStore
from .core.storage import VaultStorage


def create_storage(settings: Settings) -> VaultStorage:
    github = None
    drive = None
    if settings.github_enabled:
        github = GitHubStore(
            token=settings.github_token,
            owner=settings.github_owner,
            repo=settings.github_repo,
            branch=settings.github_branch,
            data_dir=settings.data_dir,
        )
    if settings.drive_enabled:
        drive = GoogleDriveStore(
            client_b64=settings.google_client_b64,
            token_b64=settings.google_token_b64,
            folder_id=settings.google_drive_folder_id,
        )
    storage = VaultStorage(
        github=github,
        data_dir=settings.data_dir,
        max_records_per_shard=settings.max_records_per_shard,
        drive=drive,
    )
    storage.initialize()
    return storage
