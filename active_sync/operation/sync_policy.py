"""Política central para definição automática do período de sincronização."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
import logging
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from active_sync.config import (
    ApplicationSettings,
    InitialLoadMode,
    ProcessingProfile,
)
from active_sync.persistence import DatabaseManager

from .history import SYNC_HISTORY_TABLE
from .models import SyncCommand, SyncMode, SyncStatus, SyncValidationError


SYNC_TIMEZONE = ZoneInfo("America/Sao_Paulo")


class SyncPolicyMode(StrEnum):
    INITIAL_LOAD = "INITIAL_LOAD"
    INCREMENTAL = "INCREMENTAL"
    RECOVERY = "RECOVERY"
    PERIOD = "PERIOD"
    FULL = "FULL"


@dataclass(frozen=True, slots=True)
class ResolvedSyncPeriod:
    start_date: date
    end_date: date
    policy_mode: SyncPolicyMode
    reason: str


class SyncPeriodResolver:
    """Decide o período em um único ponto sem alterar o pipeline de importação."""

    def __init__(
        self,
        settings: ApplicationSettings,
        logger: logging.Logger,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.logger = logger
        self.now = now or (lambda: datetime.now(SYNC_TIMEZONE))

    def resolve(self, command: SyncCommand) -> ResolvedSyncPeriod:
        current = self._today()
        if command.mode is SyncMode.PERIOD:
            if command.start_date is None or command.end_date is None:
                raise SyncValidationError(
                    "Datas inicial e final sao obrigatorias para PERIODO."
                )
            resolved = ResolvedSyncPeriod(
                command.start_date,
                command.end_date,
                SyncPolicyMode.PERIOD,
                "Período informado explicitamente pelo operador.",
            )
        elif command.mode is SyncMode.FULL:
            if self.settings.sync_full_start_date is None:
                raise SyncValidationError(
                    "ACTIVE_SYNC_FULL_START_DATE e obrigatoria para FULL."
                )
            resolved = ResolvedSyncPeriod(
                self.settings.sync_full_start_date,
                current,
                SyncPolicyMode.FULL,
                "Carga completa solicitada explicitamente.",
            )
        elif command.mode is SyncMode.INCREMENTAL:
            resolved = self._automatic_period(current)
        else:
            raise SyncValidationError(
                f"O modo {command.mode.value} não utiliza resolução de período."
            )
        self._validate_dates(resolved.start_date, resolved.end_date, current)
        self.logger.info(
            "sync_period_resolved",
            extra={
                "request_id": getattr(command, "request_id", None),
                "policy_mode": resolved.policy_mode.value,
                "period_start": resolved.start_date.isoformat(),
                "period_end": resolved.end_date.isoformat(),
                "reason": resolved.reason,
            },
        )
        return resolved

    def _automatic_period(self, current: date) -> ResolvedSyncPeriod:
        if not self._has_movements():
            return ResolvedSyncPeriod(
                self._initial_start(current),
                current,
                SyncPolicyMode.INITIAL_LOAD,
                "A tabela principal não possui movimentos.",
            )
        if self._latest_completed_status() is SyncStatus.ERROR:
            days = self.settings.sync_recovery_lookback_days
            return ResolvedSyncPeriod(
                current - timedelta(days=days),
                current,
                SyncPolicyMode.RECOVERY,
                f"A última sincronização finalizada terminou com erro; janela de {days} dias.",
            )
        days = self.settings.sync_incremental_lookback_days
        return ResolvedSyncPeriod(
            current - timedelta(days=days),
            current,
            SyncPolicyMode.INCREMENTAL,
            f"A base já possui movimentos; janela móvel de {days} dias.",
        )

    def _initial_start(self, current: date) -> date:
        if self.settings.sync_initial_load_mode is InitialLoadMode.CURRENT_MONTH:
            return current.replace(day=1)
        raise SyncValidationError(
            "A estratégia configurada para carga inicial não é suportada."
        )

    def _has_movements(self) -> bool:
        table = (
            "supertrack_movements"
            if self.settings.processing_profile is ProcessingProfile.SUPERTRACK
            else "performance_entrega"
        )
        with DatabaseManager(self._database_path()) as database:
            exists = database.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if exists is None:
                return False
            row = database.execute(
                f'SELECT EXISTS(SELECT 1 FROM "{table}" LIMIT 1) AS populated'
            ).fetchone()
        return bool(row["populated"])

    def _latest_completed_status(self) -> SyncStatus | None:
        with DatabaseManager(self._database_path()) as database:
            exists = database.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (SYNC_HISTORY_TABLE,),
            ).fetchone()
            if exists is None:
                return None
            row = database.execute(
                f'''SELECT status FROM "{SYNC_HISTORY_TABLE}"
                    WHERE status IN (?, ?)
                    ORDER BY id DESC LIMIT 1''',
                (SyncStatus.SUCCESS.value, SyncStatus.ERROR.value),
            ).fetchone()
        return SyncStatus(str(row["status"])) if row is not None else None

    def _database_path(self) -> Path:
        if self.settings.database_path is None:
            raise SyncValidationError("Banco operacional nao configurado.")
        return self.settings.database_path

    def _today(self) -> date:
        current = self.now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=SYNC_TIMEZONE)
        else:
            current = current.astimezone(SYNC_TIMEZONE)
        return current.date()

    @staticmethod
    def _validate_dates(start_date: date, end_date: date, current: date) -> None:
        if start_date > end_date:
            raise SyncValidationError("A data final nao pode ser menor que a inicial.")
        if end_date > current:
            raise SyncValidationError("Datas futuras nao sao permitidas.")
