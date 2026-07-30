"""Backup não crítico dos ZIPs validados após a sincronização."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
from threading import Lock
from typing import Protocol
from zoneinfo import ZoneInfo

from .base import FileStorage


BACKUP_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True, slots=True)
class BackupResult:
    uploaded: int = 0
    failed: int = 0


class SyncBackup(Protocol):
    """Porta executada somente após a conclusão funcional da sincronização."""

    enabled: bool

    def backup_files(
        self,
        files: tuple[Path, ...],
        *,
        completed_at: datetime,
        request_id: str,
    ) -> BackupResult: ...


class DisabledSyncBackup:
    """No-op usado quando o Google Drive está desligado ou indisponível."""

    enabled = False

    def backup_files(
        self,
        files: tuple[Path, ...],
        *,
        completed_at: datetime,
        request_id: str,
    ) -> BackupResult:
        del files, completed_at, request_id
        return BackupResult()


class BestEffortDriveBackup:
    """Envia ZIPs sem propagar qualquer falha para a sincronização."""

    enabled = True

    def __init__(self, storage: FileStorage, logger: logging.Logger) -> None:
        self.storage = storage
        self.logger = logger
        self._lock = Lock()

    def backup_files(
        self,
        files: tuple[Path, ...],
        *,
        completed_at: datetime,
        request_id: str,
    ) -> BackupResult:
        if not files:
            return BackupResult()
        local_time = self._local_time(completed_at)
        hierarchy = ("Active Sync", f"{local_time.year:04d}", f"{local_time.month:02d}")
        with self._lock:
            try:
                directory_id = self.storage.ensure_directory(hierarchy)
            except Exception as error:
                self._log_failure(
                    request_id=request_id,
                    file_name=None,
                    error=error,
                    stage="directory",
                )
                return BackupResult(failed=len(files))

            uploaded = failed = 0
            for source in files:
                try:
                    self.storage.store_file(
                        source,
                        content_type="application/zip",
                        directory_id=directory_id,
                    )
                except Exception as error:
                    failed += 1
                    self._log_failure(
                        request_id=request_id,
                        file_name=source.name,
                        error=error,
                        stage="upload",
                    )
                else:
                    uploaded += 1
                    self.logger.info(
                        "sync_backup_uploaded",
                        extra={
                            "request_id": request_id,
                            "file_name": source.name,
                            "backup_path": "/".join(hierarchy),
                        },
                    )
        return BackupResult(uploaded=uploaded, failed=failed)

    def _log_failure(
        self,
        *,
        request_id: str,
        file_name: str | None,
        error: Exception,
        stage: str,
    ) -> None:
        self.logger.error(
            "sync_backup_failed",
            extra={
                "request_id": request_id,
                "file_name": file_name,
                "backup_stage": stage,
                "error_type": type(error).__name__,
                "non_critical": True,
            },
            exc_info=self.logger.isEnabledFor(logging.DEBUG),
        )

    @staticmethod
    def _local_time(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=BACKUP_TIMEZONE)
        return value.astimezone(BACKUP_TIMEZONE)
