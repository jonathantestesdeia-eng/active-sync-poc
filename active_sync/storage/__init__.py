"""Infraestrutura opcional de armazenamento externo."""

from .backup import (
    BACKUP_TIMEZONE,
    BackupResult,
    BestEffortDriveBackup,
    DisabledSyncBackup,
    SyncBackup,
)
from .base import DisabledFileStorage, FileStorage, StoredFile
from .factory import create_file_storage, create_sync_backup
from .google_drive import (
    DRIVE_FILE_SCOPE,
    DRIVE_FOLDER_MIME_TYPE,
    GoogleDriveConfig,
    GoogleDriveStorage,
)

__all__ = [
    "BACKUP_TIMEZONE",
    "BackupResult",
    "BestEffortDriveBackup",
    "DRIVE_FILE_SCOPE",
    "DRIVE_FOLDER_MIME_TYPE",
    "DisabledFileStorage",
    "DisabledSyncBackup",
    "FileStorage",
    "GoogleDriveConfig",
    "GoogleDriveStorage",
    "StoredFile",
    "SyncBackup",
    "create_file_storage",
    "create_sync_backup",
]
