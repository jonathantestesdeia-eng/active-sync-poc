"""Composição da infraestrutura de armazenamento, ainda fora do pipeline."""

from __future__ import annotations

import logging

from active_sync.config import ApplicationSettings

from .backup import BestEffortDriveBackup, DisabledSyncBackup, SyncBackup
from .base import DisabledFileStorage, FileStorage
from .google_drive import GoogleDriveConfig, GoogleDriveStorage


def create_file_storage(
    settings: ApplicationSettings,
    logger: logging.Logger,
) -> FileStorage:
    """Cria o adapter configurado sem realizar conexão ou upload."""
    if not settings.google_drive_enabled:
        return DisabledFileStorage()
    return GoogleDriveStorage(
        GoogleDriveConfig(
            folder_id=settings.google_drive_folder_id or "",
            credentials_path=settings.google_application_credentials,
            credentials_json=settings.google_drive_credentials_json,
        ),
        logger,
    )


def create_sync_backup(
    settings: ApplicationSettings,
    logger: logging.Logger,
) -> SyncBackup:
    """Cria um backup tolerante a falhas sem tornar o Drive obrigatório."""
    if not settings.google_drive_enabled:
        return DisabledSyncBackup()
    try:
        storage = create_file_storage(settings, logger)
    except Exception as error:
        logger.error(
            "sync_backup_configuration_failed",
            extra={
                "error_type": type(error).__name__,
                "non_critical": True,
            },
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        return DisabledSyncBackup()
    return BestEffortDriveBackup(storage, logger)
