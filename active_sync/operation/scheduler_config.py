"""Persistência e aplicação da configuração administrativa do scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Protocol

from active_sync.persistence import DatabaseManager


SCHEDULER_CONFIGURATION_TABLE = "scheduler_configuration"
SCHEDULER_TIMEZONE = "America/Sao_Paulo"


@dataclass(frozen=True, slots=True)
class SchedulerConfiguration:
    enabled: bool
    run_time: time | None
    timezone: str
    updated_at: datetime


class ConfigurableScheduler(Protocol):
    def update_schedule(self, schedule: tuple[time, ...]) -> None: ...

    def next_run(self, now: datetime | None = None) -> datetime | None: ...


class SchedulerConfigurationStore:
    """Tabela singleton: impossibilita duas programações simultâneas."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(
        self,
        default_schedule: tuple[time, ...] = (),
    ) -> SchedulerConfiguration:
        default_time = default_schedule[0] if default_schedule else None
        with DatabaseManager(self.database_path) as database:
            database.execute(
                f'''CREATE TABLE IF NOT EXISTS "{SCHEDULER_CONFIGURATION_TABLE}" (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    run_time TEXT,
                    timezone TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )'''
            )
            database.execute(
                f'''INSERT OR IGNORE INTO "{SCHEDULER_CONFIGURATION_TABLE}"
                    (id, enabled, run_time, timezone, updated_at)
                    VALUES (1, ?, ?, ?, ?)''',
                (
                    int(bool(default_schedule)),
                    default_time.strftime("%H:%M") if default_time else None,
                    SCHEDULER_TIMEZONE,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            database.commit()
        return self.get()

    def get(self) -> SchedulerConfiguration:
        with DatabaseManager(self.database_path) as database:
            row = database.execute(
                f'''SELECT enabled, run_time, timezone, updated_at
                    FROM "{SCHEDULER_CONFIGURATION_TABLE}" WHERE id = 1'''
            ).fetchone()
        if row is None:
            raise RuntimeError("Configuração do scheduler não inicializada.")
        return SchedulerConfiguration(
            enabled=bool(row["enabled"]),
            run_time=(
                time.fromisoformat(str(row["run_time"]))
                if row["run_time"]
                else None
            ),
            timezone=str(row["timezone"]),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    def save(self, enabled: bool, run_time: time | None) -> SchedulerConfiguration:
        current = self.get()
        selected_time = run_time if run_time is not None else current.run_time
        if enabled and selected_time is None:
            raise ValueError("Informe um horário válido.")
        updated_at = datetime.now(timezone.utc)
        with DatabaseManager(self.database_path) as database:
            database.execute(
                f'''UPDATE "{SCHEDULER_CONFIGURATION_TABLE}" SET
                    enabled = ?, run_time = ?, timezone = ?, updated_at = ?
                    WHERE id = 1''',
                (
                    int(enabled),
                    selected_time.strftime("%H:%M") if selected_time else None,
                    SCHEDULER_TIMEZONE,
                    updated_at.isoformat(),
                ),
            )
            database.commit()
        return self.get()


class SchedulerConfigurationService:
    """Configura o scheduler existente sem criar um segundo executor."""

    def __init__(
        self,
        store: SchedulerConfigurationStore,
        scheduler: ConfigurableScheduler,
    ) -> None:
        self.store = store
        self.scheduler = scheduler

    def get(self) -> SchedulerConfiguration:
        return self.store.get()

    def save(self, enabled: bool, run_time: time | None) -> SchedulerConfiguration:
        configuration = self.store.save(enabled, run_time)
        self.scheduler.update_schedule(
            (configuration.run_time,)
            if configuration.enabled and configuration.run_time is not None
            else ()
        )
        return configuration

    def next_run(self) -> datetime | None:
        return self.scheduler.next_run()
