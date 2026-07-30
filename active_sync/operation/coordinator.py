"""Coordenacao, exclusao mutua e status das sincronizacoes."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import logging
from time import perf_counter
from typing import Callable, Protocol
from uuid import uuid4
from pathlib import Path

from active_sync.config import ProcessingProfile
from active_sync.logger import request_id_context
from active_sync.storage import DisabledSyncBackup, SyncBackup

from .history import SyncHistoryStore
from .models import (
    SyncAlreadyRunningError,
    SyncCommand,
    SyncHistoryEntry,
    SyncMode,
    SyncOrigin,
    SyncResult,
    SyncStatus,
    SyncValidationError,
)
from .notifications import (
    LoggingSyncNotifier,
    SyncNotification,
    SyncNotifier,
    SyncNotificationType,
)


class SyncPipeline(Protocol):
    def execute(self, command: SyncCommand) -> SyncResult: ...


class SyncCoordinator:
    """Ponto unico de entrada para execucoes manuais e agendadas."""

    def __init__(
        self,
        pipeline: SyncPipeline,
        history: SyncHistoryStore,
        logger: logging.Logger,
        *,
        now: Callable[[], datetime] | None = None,
        profile: ProcessingProfile = ProcessingProfile.SUPERTRACK,
        notifier: SyncNotifier | None = None,
        backup: SyncBackup | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.history = history
        self.logger = logger
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.profile = profile
        self.notifier = notifier or LoggingSyncNotifier(logger)
        self.backup = backup or DisabledSyncBackup()
        self._guard = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._backup_tasks: set[asyncio.Task[None]] = set()
        self._running: SyncHistoryEntry | None = None
        self._next_run_provider: Callable[[], datetime | None] = lambda: None

    def set_next_run_provider(self, provider: Callable[[], datetime | None]) -> None:
        self._next_run_provider = provider

    async def start(
        self,
        mode: SyncMode,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        user: str = "system",
        origin: SyncOrigin = SyncOrigin.MANUAL,
        source_file: Path | None = None,
        reprocess_of_id: int | None = None,
    ) -> SyncHistoryEntry:
        self._validate(mode, start_date, end_date, source_file)
        async with self._guard:
            if self._task is not None and not self._task.done():
                raise SyncAlreadyRunningError("Ja existe uma sincronizacao em execucao.")
            command = SyncCommand(
                request_id=str(uuid4()),
                mode=mode,
                origin=origin,
                user=user.strip() or "system",
                started_at=self.now(),
                start_date=start_date,
                end_date=end_date,
                profile=self.profile,
                source_file=source_file,
                reprocess_of_id=reprocess_of_id,
            )
            entry = self.history.begin(command)
            self._running = entry
            self.logger.info(
                "sync_started",
                extra={
                    "request_id": command.request_id,
                    "sync_id": entry.id,
                    "mode": command.mode.value,
                    "file": source_file.name if source_file else None,
                    "start_date": start_date,
                    "end_date": end_date,
                    "origin": origin.value,
                    "profile": command.profile.value,
                },
            )
            self._task = asyncio.create_task(self._execute(entry.id, command))
            return entry

    @staticmethod
    def _validate(
        mode: SyncMode,
        start_date: date | None,
        end_date: date | None,
        source_file: Path | None,
    ) -> None:
        if mode is SyncMode.PERIOD and (start_date is None or end_date is None):
            raise SyncValidationError("Datas inicial e final sao obrigatorias para PERIODO.")
        if mode is not SyncMode.PERIOD and (start_date is not None or end_date is not None):
            raise SyncValidationError("Datas so podem ser informadas no modo PERIODO.")
        if mode is SyncMode.FILE and source_file is None:
            raise SyncValidationError("Arquivo obrigatorio para reprocessamento por arquivo.")
        if mode is not SyncMode.FILE and source_file is not None:
            raise SyncValidationError("Arquivo so pode ser informado no modo ARQUIVO.")
        if start_date and end_date and start_date > end_date:
            raise SyncValidationError("A data final nao pode ser menor que a inicial.")
        today = date.today()
        if (start_date and start_date > today) or (end_date and end_date > today):
            raise SyncValidationError("Datas futuras nao sao permitidas.")

    async def _execute(self, entry_id: int, command: SyncCommand) -> None:
        started = perf_counter()
        result = SyncResult()
        error_message: str | None = None
        status = SyncStatus.SUCCESS
        with request_id_context(command.request_id):
            try:
                result = await asyncio.to_thread(self.pipeline.execute, command)
            except Exception as error:
                status = SyncStatus.ERROR
                error_message = str(error)[:2000]
                if command.source_file is not None:
                    result = SyncResult(source_files=(command.source_file.name,))
                self.logger.error(
                    "sync_failed",
                    extra={
                        "request_id": command.request_id,
                        "mode": command.mode.value,
                        "profile": command.profile.value,
                    },
                    exc_info=self.logger.isEnabledFor(logging.DEBUG),
                )
            finally:
                finished_at = self.now()
                duration_ms = (perf_counter() - started) * 1000
                self.history.finish(
                    entry_id,
                    status,
                    finished_at,
                    duration_ms,
                    result,
                    error_message,
                )
                self.logger.info(
                    "sync_finished",
                    extra={
                        "request_id": command.request_id,
                        "sync_id": entry_id,
                        "started_at": command.started_at,
                        "finished_at": finished_at,
                        "duration_ms": round(duration_ms, 3),
                        "file": list(result.source_files),
                        "mode": command.mode.value,
                        "records_read": result.records_read,
                        "records_inserted": result.records_inserted,
                        "records_updated": result.records_updated,
                        "records_ignored": result.records_ignored,
                        "records_cancelled": result.records_cancelled,
                        "status": status.value,
                        "error": error_message,
                    },
                )
                self.notifier.notify(
                    SyncNotification(
                        event=(
                            SyncNotificationType.COMPLETED
                            if status is SyncStatus.SUCCESS
                            else SyncNotificationType.FAILED
                        ),
                        request_id=command.request_id,
                        occurred_at=finished_at,
                        details={
                            "sync_id": entry_id,
                            "mode": command.mode.value,
                            "status": status.value,
                            "error": error_message,
                        },
                    )
                )
                self._running = None
                if (
                    status is SyncStatus.SUCCESS
                    and result.backup_files
                    and self.backup.enabled
                ):
                    backup_task = asyncio.create_task(
                        self._run_backup(
                            result.backup_files,
                            completed_at=finished_at,
                            request_id=command.request_id,
                        )
                    )
                    self._backup_tasks.add(backup_task)
                    backup_task.add_done_callback(self._backup_tasks.discard)

    async def _run_backup(
        self,
        files: tuple[Path, ...],
        *,
        completed_at: datetime,
        request_id: str,
    ) -> None:
        try:
            await asyncio.to_thread(
                self.backup.backup_files,
                files,
                completed_at=completed_at,
                request_id=request_id,
            )
        except Exception:
            self.logger.error(
                "sync_backup_unexpected_failure",
                extra={
                    "request_id": request_id,
                    "non_critical": True,
                },
                exc_info=self.logger.isEnabledFor(logging.DEBUG),
            )

    async def wait_current(self) -> None:
        task = self._task
        if task is not None:
            await task

    async def wait_backups(self) -> None:
        """Aguarda backups pendentes somente quando solicitado explicitamente."""
        tasks = tuple(self._backup_tasks)
        if tasks:
            await asyncio.gather(*tasks)

    def status(self) -> dict[str, object]:
        latest = self.history.latest()
        return {
            "running": self._task is not None and not self._task.done(),
            "current": self._running,
            "latest": latest,
            "next_scheduled_at": self._next_run_provider(),
        }

    def list_history(self, limit: int, offset: int) -> tuple[SyncHistoryEntry, ...]:
        return self.history.list(limit, offset)

    def get_history(self, entry_id: int) -> SyncHistoryEntry | None:
        return self.history.get(entry_id)
