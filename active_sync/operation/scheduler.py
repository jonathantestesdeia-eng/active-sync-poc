"""Agendador diario leve, sem horarios hardcoded nem dependencia externa."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
import logging
from zoneinfo import ZoneInfo

from .coordinator import SyncCoordinator
from .models import SyncAlreadyRunningError, SyncMode, SyncOrigin


SCHEDULER_TIMEZONE = ZoneInfo("America/Sao_Paulo")


class SyncScheduler:
    def __init__(
        self,
        coordinator: SyncCoordinator,
        schedule: tuple[time, ...],
        logger: logging.Logger,
    ) -> None:
        self.coordinator = coordinator
        self.schedule = schedule
        self.logger = logger
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._configuration_changed = asyncio.Event()
        coordinator.set_next_run_provider(self.next_run)

    def next_run(self, now: datetime | None = None) -> datetime | None:
        if not self.schedule:
            return None
        current = now or datetime.now(SCHEDULER_TIMEZONE)
        candidates = [datetime.combine(current.date(), item, current.tzinfo) for item in self.schedule]
        for candidate in candidates:
            if candidate > current:
                return candidate
        return datetime.combine(current.date() + timedelta(days=1), self.schedule[0], current.tzinfo)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run())

    def update_schedule(self, schedule: tuple[time, ...]) -> None:
        """Aplica uma configuração nova e desperta o loop imediatamente."""
        self.schedule = tuple(sorted(set(schedule)))
        self._configuration_changed.set()

    async def stop(self) -> None:
        self._stopped.set()
        self._configuration_changed.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stopped.is_set():
            next_run = self.next_run()
            delay = (
                max(
                    (
                        next_run
                        - datetime.now(next_run.tzinfo or SCHEDULER_TIMEZONE)
                    ).total_seconds(),
                    0,
                )
                if next_run is not None
                else None
            )
            stopped, changed = await self._wait(delay)
            if stopped:
                return
            if changed:
                continue
            try:
                await self.coordinator.start(
                    SyncMode.INCREMENTAL,
                    user="scheduler",
                    origin=SyncOrigin.SCHEDULED,
                )
            except SyncAlreadyRunningError:
                self.logger.warning(
                    "scheduled_sync_skipped_concurrent_execution",
                    extra={"request_id": None, "mode": SyncMode.INCREMENTAL.value},
                )

    async def _wait(self, delay: float | None) -> tuple[bool, bool]:
        stop_task = asyncio.create_task(self._stopped.wait())
        change_task = asyncio.create_task(self._configuration_changed.wait())
        done, pending = await asyncio.wait(
            {stop_task, change_task},
            timeout=delay,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        changed = change_task in done and change_task.result()
        if changed:
            self._configuration_changed.clear()
        return self._stopped.is_set(), bool(changed)
