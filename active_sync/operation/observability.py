"""Leituras operacionais da API, banco, storage e histórico de sincronizações."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path

from active_sync.config import ApplicationSettings, ProcessingProfile
from active_sync.persistence import DatabaseManager, MigrationManager

from .history import SyncHistoryStore
from .models import SyncHistoryEntry


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    status: str
    database: str
    api: str
    storage: str
    version: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class StatisticsSnapshot:
    total_movements: int
    total_returns: int
    total_cancelled: int
    first_sync_at: datetime | None
    last_sync_at: datetime | None
    sync_count: int
    failure_count: int
    average_duration_ms: float | None
    maximum_duration_ms: float | None
    minimum_duration_ms: float | None
    seconds_since_last_execution: float | None


@dataclass(frozen=True, slots=True)
class SystemStatusSnapshot:
    api: str
    database: str
    active_profile: str
    total_records: int
    last_sync: SyncHistoryEntry | None
    version: str
    environment: str
    uptime_seconds: float
    health: str


class OperationalObservability:
    """Serviço somente leitura, isolado das regras de negócio homologadas."""

    def __init__(
        self,
        settings: ApplicationSettings,
        history: SyncHistoryStore,
        started_at: datetime,
    ) -> None:
        self.settings = settings
        self.history = history
        self.started_at = started_at

    def health(self) -> HealthSnapshot:
        database = self._database_health()
        storage = self._storage_health()
        overall = "ok" if database == "ok" and storage == "ok" else "degraded"
        return HealthSnapshot(
            status=overall,
            database=database,
            api="ok",
            storage=storage,
            version=self.settings.version,
            timestamp=datetime.now(timezone.utc),
        )

    def statistics(self) -> StatisticsSnapshot:
        aggregate = self.history.aggregate()
        total_movements, total_returns = self._movement_counts()
        last_sync_at = aggregate["last_sync_at"]
        now = datetime.now(timezone.utc)
        seconds_since = (
            max((now - self._aware(last_sync_at)).total_seconds(), 0.0)
            if isinstance(last_sync_at, datetime)
            else None
        )
        return StatisticsSnapshot(
            total_movements=total_movements,
            total_returns=total_returns,
            total_cancelled=int(aggregate["cancelled_total"]),
            first_sync_at=aggregate["first_sync_at"],
            last_sync_at=last_sync_at,
            sync_count=int(aggregate["sync_count"]),
            failure_count=int(aggregate["failure_count"]),
            average_duration_ms=aggregate["average_duration_ms"],
            maximum_duration_ms=aggregate["maximum_duration_ms"],
            minimum_duration_ms=aggregate["minimum_duration_ms"],
            seconds_since_last_execution=seconds_since,
        )

    def system_status(self) -> SystemStatusSnapshot:
        health = self.health()
        total_movements, _ = self._movement_counts()
        now = datetime.now(timezone.utc)
        return SystemStatusSnapshot(
            api=health.api,
            database=health.database,
            active_profile=self.settings.processing_profile.value,
            total_records=total_movements,
            last_sync=self.history.latest(),
            version=self.settings.version,
            environment=self.settings.environment.value,
            uptime_seconds=max(
                (now - self._aware(self.started_at)).total_seconds(), 0.0
            ),
            health=health.status,
        )

    def _database_health(self) -> str:
        try:
            with DatabaseManager(self._database_path()) as database:
                database.execute("SELECT 1").fetchone()
            return "ok"
        except Exception:
            return "unavailable"

    def _storage_health(self) -> str:
        directory = self.settings.sync_work_dir
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return "ok" if os.access(directory, os.R_OK | os.W_OK) else "unavailable"
        except OSError:
            return "unavailable"

    def _movement_counts(self) -> tuple[int, int]:
        with DatabaseManager(self._database_path()) as database:
            MigrationManager(database).migrate()
            if self.settings.processing_profile is ProcessingProfile.SUPERTRACK:
                row = database.execute(
                    '''SELECT COUNT(*) AS total,
                        SUM(CASE WHEN UPPER(COALESCE(tipo_cte, ''))
                            LIKE '%DEVOLU%' THEN 1 ELSE 0 END) AS returns
                    FROM "supertrack_movements"'''
                ).fetchone()
            else:
                row = database.execute(
                    '''SELECT COUNT(*) AS total,
                        SUM(CASE WHEN "Flag Devolução NF" = 1
                            THEN 1 ELSE 0 END) AS returns
                    FROM "performance_entrega"'''
                ).fetchone()
        return int(row["total"] or 0), int(row["returns"] or 0)

    def _database_path(self) -> Path:
        if self.settings.database_path is None:
            raise RuntimeError("Banco operacional não configurado.")
        return self.settings.database_path

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
