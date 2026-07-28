"""Reprocessamento controlado sobre o pipeline operacional único."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from .coordinator import SyncCoordinator
from .history import SyncHistoryStore
from .models import SyncHistoryEntry, SyncMode
from .notifications import (
    SyncNotification,
    SyncNotifier,
    SyncNotificationType,
)
from .models import SyncValidationError


class SyncReprocessor:
    def __init__(
        self,
        coordinator: SyncCoordinator,
        history: SyncHistoryStore,
        import_directory: Path,
        notifier: SyncNotifier,
    ) -> None:
        self.coordinator = coordinator
        self.history = history
        self.import_directory = import_directory.resolve()
        self.notifier = notifier

    async def period(
        self,
        start_date: date,
        end_date: date,
        *,
        user: str,
        reprocess_of_id: int | None = None,
    ) -> SyncHistoryEntry:
        return await self.coordinator.start(
            SyncMode.PERIOD,
            start_date=start_date,
            end_date=end_date,
            user=user,
            reprocess_of_id=reprocess_of_id,
        )

    async def file(self, file_name: str, *, user: str) -> SyncHistoryEntry:
        source_file = self._resolve_file(file_name)
        return await self.coordinator.start(
            SyncMode.FILE,
            source_file=source_file,
            user=user,
        )

    async def sync_id(self, entry_id: int, *, user: str) -> SyncHistoryEntry:
        original = self.history.get(entry_id)
        if original is None:
            raise SyncValidationError("Sincronização informada não foi encontrada.")
        for file_name in original.source_files:
            candidate = self.import_directory / Path(file_name).name
            if candidate.is_file():
                return await self.coordinator.start(
                    SyncMode.FILE,
                    source_file=candidate,
                    user=user,
                    reprocess_of_id=entry_id,
                )
        if original.start_date is not None and original.end_date is not None:
            return await self.period(
                original.start_date,
                original.end_date,
                user=user,
                reprocess_of_id=entry_id,
            )
        if original.mode in {SyncMode.INCREMENTAL, SyncMode.FULL}:
            return await self.coordinator.start(
                original.mode,
                user=user,
                reprocess_of_id=entry_id,
            )
        raise SyncValidationError(
            "A execução não possui período nem arquivo disponível para reprocessamento."
        )

    def _resolve_file(self, file_name: str) -> Path:
        requested = Path(file_name)
        if requested.is_absolute():
            candidate = requested.resolve()
        else:
            candidate = (self.import_directory / requested).resolve()
        valid = (
            candidate.suffix.casefold() == ".xlsx"
            and candidate.is_file()
            and candidate.is_relative_to(self.import_directory)
        )
        if not valid:
            request_id = f"invalid-file-{uuid4()}"
            self.notifier.notify(
                SyncNotification(
                    event=SyncNotificationType.INVALID_FILE,
                    request_id=request_id,
                    occurred_at=datetime.now(timezone.utc),
                    details={"file": file_name},
                )
            )
            raise SyncValidationError(
                "Arquivo inválido. Utilize um .xlsx existente em runtime/imports."
            )
        return candidate
