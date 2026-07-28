"""Contratos da camada operacional de sincronizacao."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from active_sync.config import ProcessingProfile


class SyncMode(StrEnum):
    INCREMENTAL = "INCREMENTAL"
    PERIOD = "PERIODO"
    FULL = "FULL"
    FILE = "ARQUIVO"


class SyncOrigin(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "agendada"


class SyncStatus(StrEnum):
    RUNNING = "EM_EXECUCAO"
    SUCCESS = "SUCESSO"
    ERROR = "ERRO"


@dataclass(frozen=True, slots=True)
class SyncCommand:
    request_id: str
    mode: SyncMode
    origin: SyncOrigin
    user: str
    started_at: datetime
    start_date: date | None = None
    end_date: date | None = None
    profile: ProcessingProfile = ProcessingProfile.SUPERTRACK
    source_file: Path | None = None
    reprocess_of_id: int | None = None


@dataclass(frozen=True, slots=True)
class SyncResult:
    records_read: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_ignored: int = 0
    records_cancelled: int = 0
    source_files: tuple[str, ...] = ()
    period_start: date | None = None
    period_end: date | None = None
    warnings: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()

    @property
    def records_processed(self) -> int:
        return (
            self.records_inserted
            + self.records_updated
            + self.records_ignored
            + self.records_cancelled
        )

    def __add__(self, other: SyncResult) -> SyncResult:
        return SyncResult(
            records_read=self.records_read + other.records_read,
            records_inserted=self.records_inserted + other.records_inserted,
            records_updated=self.records_updated + other.records_updated,
            records_ignored=self.records_ignored + other.records_ignored,
            records_cancelled=self.records_cancelled + other.records_cancelled,
            source_files=tuple(dict.fromkeys(self.source_files + other.source_files)),
            period_start=min(
                value
                for value in (self.period_start, other.period_start)
                if value is not None
            )
            if self.period_start is not None or other.period_start is not None
            else None,
            period_end=max(
                value
                for value in (self.period_end, other.period_end)
                if value is not None
            )
            if self.period_end is not None or other.period_end is not None
            else None,
            warnings=tuple(dict.fromkeys(self.warnings + other.warnings)),
            messages=tuple(dict.fromkeys(self.messages + other.messages)),
        )


@dataclass(frozen=True, slots=True)
class SyncHistoryEntry:
    id: int
    request_id: str
    mode: SyncMode
    started_at: datetime
    finished_at: datetime | None
    duration_ms: float | None
    status: SyncStatus
    records_read: int
    records_inserted: int
    records_updated: int
    records_ignored: int
    errors: str | None
    user: str
    origin: SyncOrigin
    profile: ProcessingProfile = ProcessingProfile.SUPERTRACK
    start_date: date | None = None
    end_date: date | None = None
    source_files: tuple[str, ...] = ()
    records_cancelled: int = 0
    warnings: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    reprocess_of_id: int | None = None

    @property
    def records_processed(self) -> int:
        return (
            self.records_inserted
            + self.records_updated
            + self.records_ignored
            + self.records_cancelled
        )


class SyncError(RuntimeError):
    """Erro base da operacao de sincronizacao."""


class SyncAlreadyRunningError(SyncError):
    """Existe uma execucao protegida pelo lock global."""


class SyncValidationError(SyncError):
    """Comando operacional invalido."""
