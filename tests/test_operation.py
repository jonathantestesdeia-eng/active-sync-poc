from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
import logging
from pathlib import Path
from threading import Event

import pytest

from active_sync.config import AppEnvironment, ApplicationSettings
from active_sync.operation import (
    OperationalSyncPipeline,
    OperationalObservability,
    LoggingSyncNotifier,
    SyncAlreadyRunningError,
    SyncCoordinator,
    SyncHistoryStore,
    SyncMode,
    SyncOrigin,
    SyncResult,
    SyncReprocessor,
    SyncScheduler,
    SchedulerConfigurationService,
    SchedulerConfigurationStore,
    SyncStatus,
    SyncValidationError,
)


def settings(tmp_path: Path, **overrides) -> ApplicationSettings:
    values = {
        "environment": AppEnvironment.TEST,
        "api_key": "test-api-key-123456789",
        "allowed_origins": ("http://testserver",),
        "database_path": tmp_path / "operation.sqlite3",
        "version": "test",
        "build_date": "test",
        "sync_full_start_date": date(2026, 7, 1),
        "sync_incremental_lookback_days": 3,
        "sync_work_dir": tmp_path / "runtime",
    }
    values.update(overrides)
    return ApplicationSettings(**values)


class ImmediatePipeline:
    def __init__(self, result: SyncResult | None = None) -> None:
        self.commands = []
        self.result = result or SyncResult(10, 4, 2, 4)

    def execute(self, command):
        self.commands.append(command)
        return self.result


class BlockingPipeline(ImmediatePipeline):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()

    def execute(self, command):
        self.commands.append(command)
        self.started.set()
        self.release.wait(timeout=5)
        return self.result


def coordinator(tmp_path: Path, pipeline) -> SyncCoordinator:
    history = SyncHistoryStore(tmp_path / "operation.sqlite3")
    history.initialize()
    return SyncCoordinator(pipeline, history, logging.getLogger("test.operation"))


def test_manual_incremental_execution_and_history(tmp_path: Path) -> None:
    async def scenario() -> None:
        pipeline = ImmediatePipeline()
        sync = coordinator(tmp_path, pipeline)
        started = await sync.start(SyncMode.INCREMENTAL, user="operador")
        assert started.status is SyncStatus.RUNNING
        await sync.wait_current()
        history = sync.list_history(10, 0)
        assert len(history) == 1
        assert history[0].status is SyncStatus.SUCCESS
        assert history[0].records_processed == 10
        assert history[0].user == "operador"
        assert pipeline.commands[0].mode is SyncMode.INCREMENTAL

    asyncio.run(scenario())


def test_sync_execution_audits_period_files_and_cancellations(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        pipeline = ImmediatePipeline(
            SyncResult(
                records_read=10,
                records_inserted=4,
                records_updated=2,
                records_ignored=3,
                records_cancelled=1,
                source_files=("active_01_07.xlsx", "active_07_08.xlsx"),
            )
        )
        sync = coordinator(tmp_path, pipeline)
        started = await sync.start(
            SyncMode.PERIOD,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 8),
        )
        await sync.wait_current()
        detail = sync.get_history(started.id)
        assert detail is not None
        assert detail.start_date == date(2026, 7, 1)
        assert detail.end_date == date(2026, 7, 8)
        assert detail.source_files == (
            "active_01_07.xlsx",
            "active_07_08.xlsx",
        )
        assert detail.records_cancelled == 1
        assert detail.records_processed == 10

        from active_sync.persistence import DatabaseManager

        with DatabaseManager(tmp_path / "operation.sqlite3") as database:
            table = database.execute(
                "SELECT type FROM sqlite_master WHERE name = 'sync_execution'"
            ).fetchone()
        assert table["type"] == "table"

    asyncio.run(scenario())


def test_period_full_and_date_validation(tmp_path: Path) -> None:
    async def scenario() -> None:
        pipeline = ImmediatePipeline()
        sync = coordinator(tmp_path, pipeline)
        await sync.start(
            SyncMode.PERIOD,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 7),
        )
        await sync.wait_current()
        await sync.start(SyncMode.FULL)
        await sync.wait_current()
        assert [command.mode for command in pipeline.commands] == [SyncMode.PERIOD, SyncMode.FULL]
        with pytest.raises(SyncValidationError):
            await sync.start(
                SyncMode.PERIOD,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 1),
            )
        with pytest.raises(SyncValidationError, match="futuras"):
            await sync.start(
                SyncMode.PERIOD,
                start_date=date.today() + timedelta(days=1),
                end_date=date.today() + timedelta(days=1),
            )

    asyncio.run(scenario())


def test_concurrent_execution_is_rejected(tmp_path: Path) -> None:
    async def scenario() -> None:
        pipeline = BlockingPipeline()
        sync = coordinator(tmp_path, pipeline)
        await sync.start(SyncMode.INCREMENTAL)
        await asyncio.to_thread(pipeline.started.wait, 2)
        with pytest.raises(SyncAlreadyRunningError):
            await sync.start(SyncMode.FULL)
        pipeline.release.set()
        await sync.wait_current()

    asyncio.run(scenario())


def test_pipeline_uses_single_window_implementation_for_all_modes(tmp_path: Path) -> None:
    fixed_today = date(2026, 7, 22)
    pipeline = OperationalSyncPipeline(
        settings(tmp_path), logging.getLogger("test.pipeline"), today=lambda: fixed_today
    )
    incremental = type("Command", (), {"mode": SyncMode.INCREMENTAL, "start_date": None, "end_date": None})
    full = type("Command", (), {"mode": SyncMode.FULL, "start_date": None, "end_date": None})
    period = type(
        "Command",
        (),
        {"mode": SyncMode.PERIOD, "start_date": date(2026, 7, 1), "end_date": date(2026, 7, 22)},
    )
    assert pipeline._resolve_dates(incremental) == (date(2026, 7, 20), fixed_today)
    assert pipeline._resolve_dates(full) == (date(2026, 7, 1), fixed_today)
    windows = pipeline._windows(*pipeline._resolve_dates(period))
    assert [(item.date_from, item.date_to) for item in windows] == [
        (date(2026, 7, 1), date(2026, 7, 7)),
        (date(2026, 7, 8), date(2026, 7, 14)),
        (date(2026, 7, 15), date(2026, 7, 21)),
        (date(2026, 7, 22), date(2026, 7, 22)),
    ]


def test_scheduler_calculates_multiple_daily_times(tmp_path: Path) -> None:
    sync = coordinator(tmp_path, ImmediatePipeline())
    scheduler = SyncScheduler(
        sync,
        (time(8), time(12), time(18)),
        logging.getLogger("test.scheduler"),
    )
    current = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
    assert scheduler.next_run(current) == datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    after_last = datetime(2026, 7, 22, 19, tzinfo=timezone.utc)
    assert scheduler.next_run(after_last) == datetime(2026, 7, 23, 8, tzinfo=timezone.utc)


def test_scheduler_configuration_is_single_persistent_and_dynamic(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "operation.sqlite3"
    store = SchedulerConfigurationStore(database_path)
    initial = store.initialize()
    sync = coordinator(tmp_path, ImmediatePipeline())
    scheduler = SyncScheduler(sync, (), logging.getLogger("test.scheduler"))
    service = SchedulerConfigurationService(store, scheduler)

    assert initial.enabled is False
    assert service.next_run() is None
    enabled = service.save(True, time(6, 30))
    assert enabled.enabled is True
    assert enabled.run_time == time(6, 30)
    assert scheduler.schedule == (time(6, 30),)
    assert service.next_run() is not None

    restored = SchedulerConfigurationStore(database_path).get()
    assert restored.enabled is True
    assert restored.run_time == time(6, 30)
    disabled = service.save(False, None)
    assert disabled.enabled is False
    assert disabled.run_time == time(6, 30)
    assert scheduler.schedule == ()
    assert service.next_run() is None


def test_scheduler_automatic_execution_remains_incremental() -> None:
    source = (
        Path(__file__).parents[1]
        / "active_sync"
        / "operation"
        / "scheduler.py"
    ).read_text(encoding="utf-8")
    assert "SyncMode.INCREMENTAL" in source
    assert "SyncMode.PERIOD" not in source
    assert "SyncMode.FULL" not in source


def test_history_detail_and_error_are_persisted(tmp_path: Path) -> None:
    class FailingPipeline:
        def execute(self, command):
            raise RuntimeError("falha controlada")

    async def scenario() -> None:
        sync = coordinator(tmp_path, FailingPipeline())
        started = await sync.start(SyncMode.INCREMENTAL, origin=SyncOrigin.SCHEDULED)
        await sync.wait_current()
        detail = sync.get_history(started.id)
        assert detail is not None
        assert detail.status is SyncStatus.ERROR
        assert detail.origin is SyncOrigin.SCHEDULED
        assert detail.errors == "falha controlada"

    asyncio.run(scenario())


def test_structured_sync_log_contains_request_and_totals(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        caplog.set_level(logging.INFO, logger="test.operation")
        sync = coordinator(tmp_path, ImmediatePipeline())
        started = await sync.start(SyncMode.INCREMENTAL)
        await sync.wait_current()
        completed = next(
            record for record in caplog.records if record.message == "sync_finished"
        )
        assert completed.request_id == started.request_id
        assert completed.records_read == 10
        assert completed.records_inserted == 4
        assert completed.records_updated == 2
        assert completed.records_ignored == 4
        assert completed.records_cancelled == 0
        assert completed.status == SyncStatus.SUCCESS.value

    asyncio.run(scenario())


def test_reprocessing_uses_period_file_and_original_sync(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        pipeline = ImmediatePipeline()
        sync = coordinator(tmp_path, pipeline)
        imports = tmp_path / "runtime" / "imports"
        imports.mkdir(parents=True)
        source = imports / "active.xlsx"
        source.write_bytes(b"fixture")
        reprocessor = SyncReprocessor(
            sync,
            sync.history,
            imports,
            LoggingSyncNotifier(logging.getLogger("test.operation")),
        )

        period = await reprocessor.period(
            date(2026, 7, 1),
            date(2026, 7, 7),
            user="operador",
        )
        await sync.wait_current()
        by_file = await reprocessor.file("active.xlsx", user="operador")
        await sync.wait_current()
        repeated = await reprocessor.sync_id(period.id, user="operador")
        await sync.wait_current()

        assert period.mode is SyncMode.PERIOD
        assert by_file.mode is SyncMode.FILE
        assert repeated.mode is SyncMode.PERIOD
        assert pipeline.commands[1].source_file == source.resolve()
        assert pipeline.commands[2].reprocess_of_id == period.id
        with pytest.raises(SyncValidationError, match="Arquivo inválido"):
            await reprocessor.file("../fora.xlsx", user="operador")

    asyncio.run(scenario())


def test_observability_statistics_health_and_uptime(tmp_path: Path) -> None:
    from active_sync.persistence import DatabaseManager, MigrationManager

    database_path = tmp_path / "operation.sqlite3"
    history = SyncHistoryStore(database_path)
    history.initialize()
    application_settings = settings(tmp_path)
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        database.execute(
            '''INSERT INTO supertrack_movements (
                transportador_id, serie_cte, cte, nota_fiscal, tipo_cte,
                situacao, last_seen_request_id, last_sync_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                "T1",
                "1",
                "10",
                "100",
                "DEVOLUCAO",
                "DEVOLVIDA",
                "seed",
                "seed",
            ),
        )
        database.commit()

    async def execute() -> None:
        sync = SyncCoordinator(
            ImmediatePipeline(SyncResult(5, 2, 1, 1, 1)),
            history,
            logging.getLogger("test.operation"),
        )
        await sync.start(SyncMode.INCREMENTAL)
        await sync.wait_current()

    asyncio.run(execute())
    observed = OperationalObservability(
        application_settings,
        history,
        datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    health = observed.health()
    statistics = observed.statistics()
    status = observed.system_status()
    assert health.status == "ok"
    assert health.database == "ok"
    assert health.storage == "ok"
    assert statistics.total_movements == 1
    assert statistics.total_returns == 1
    assert statistics.total_cancelled == 1
    assert statistics.sync_count == 1
    assert statistics.failure_count == 0
    assert statistics.average_duration_ms is not None
    assert statistics.seconds_since_last_execution is not None
    assert status.total_records == 1
    assert status.last_sync is not None
    assert status.uptime_seconds >= 10
