from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from pathlib import Path

from active_sync.config import AppEnvironment, ApplicationSettings
from active_sync.operation import (
    SyncCommand,
    SyncHistoryStore,
    SyncMode,
    SyncOrigin,
    SyncPeriodResolver,
    SyncPolicyMode,
    SyncResult,
    SyncStatus,
)
from active_sync.persistence import DatabaseManager, MigrationManager


def settings(tmp_path: Path, **overrides) -> ApplicationSettings:
    values = {
        "environment": AppEnvironment.TEST,
        "api_key": "test-api-key-123456789",
        "allowed_origins": ("http://testserver",),
        "database_path": tmp_path / "policy.sqlite3",
        "version": "test",
        "build_date": "2026-07-29",
        "sync_incremental_lookback_days": 7,
        "sync_recovery_lookback_days": 14,
    }
    values.update(overrides)
    return ApplicationSettings(**values)


def command(request_id: str = "policy-request") -> SyncCommand:
    return SyncCommand(
        request_id=request_id,
        mode=SyncMode.INCREMENTAL,
        origin=SyncOrigin.MANUAL,
        user="operator",
        started_at=datetime(2026, 7, 29, 12, tzinfo=timezone.utc),
    )


def seed_movement(database_path: Path) -> None:
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        database.execute(
            '''INSERT INTO supertrack_movements (
                transportador_id, serie_cte, cte, nota_fiscal, situacao,
                last_seen_request_id, last_sync_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)''',
            ("T1", "1", "10", "100", "EM ABERTO", "seed", "seed"),
        )
        database.commit()


def record_completed_sync(
    database_path: Path,
    *,
    status: SyncStatus,
    request_id: str,
) -> None:
    history = SyncHistoryStore(database_path)
    history.initialize()
    started_at = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
    entry = history.begin(
        SyncCommand(
            request_id=request_id,
            mode=SyncMode.INCREMENTAL,
            origin=SyncOrigin.SCHEDULED,
            user="scheduler",
            started_at=started_at,
        )
    )
    history.finish(
        entry.id,
        status,
        started_at,
        1000,
        SyncResult(),
        "failure" if status is SyncStatus.ERROR else None,
    )


def resolver(
    application_settings: ApplicationSettings,
    current: datetime,
) -> SyncPeriodResolver:
    return SyncPeriodResolver(
        application_settings,
        logging.getLogger("test.sync-policy"),
        now=lambda: current,
    )


def test_empty_database_uses_current_month_initial_load(tmp_path: Path) -> None:
    policy = resolver(
        settings(tmp_path),
        datetime(2026, 7, 29, 15, tzinfo=timezone.utc),
    )

    period = policy.resolve(command())

    assert period.policy_mode is SyncPolicyMode.INITIAL_LOAD
    assert period.start_date == date(2026, 7, 1)
    assert period.end_date == date(2026, 7, 29)


def test_populated_database_without_history_uses_incremental_window(
    tmp_path: Path,
) -> None:
    application_settings = settings(tmp_path)
    assert application_settings.database_path is not None
    seed_movement(application_settings.database_path)

    period = resolver(
        application_settings,
        datetime(2026, 7, 29, 15, tzinfo=timezone.utc),
    ).resolve(command())

    assert period.policy_mode is SyncPolicyMode.INCREMENTAL
    assert period.start_date == date(2026, 7, 22)
    assert period.end_date == date(2026, 7, 29)


def test_last_successful_sync_keeps_incremental_window(tmp_path: Path) -> None:
    application_settings = settings(tmp_path)
    assert application_settings.database_path is not None
    seed_movement(application_settings.database_path)
    record_completed_sync(
        application_settings.database_path,
        status=SyncStatus.SUCCESS,
        request_id="success",
    )

    period = resolver(
        application_settings,
        datetime(2026, 7, 29, 15, tzinfo=timezone.utc),
    ).resolve(command())

    assert period.policy_mode is SyncPolicyMode.INCREMENTAL
    assert period.start_date == date(2026, 7, 22)


def test_last_failed_sync_uses_recovery_window_and_ignores_current_running(
    tmp_path: Path,
) -> None:
    application_settings = settings(tmp_path)
    assert application_settings.database_path is not None
    seed_movement(application_settings.database_path)
    record_completed_sync(
        application_settings.database_path,
        status=SyncStatus.ERROR,
        request_id="failed",
    )
    history = SyncHistoryStore(application_settings.database_path)
    history.begin(command("currently-running"))

    period = resolver(
        application_settings,
        datetime(2026, 7, 29, 15, tzinfo=timezone.utc),
    ).resolve(command())

    assert period.policy_mode is SyncPolicyMode.RECOVERY
    assert period.start_date == date(2026, 7, 15)
    assert period.end_date == date(2026, 7, 29)


def test_windows_follow_configuration(tmp_path: Path) -> None:
    incremental_settings = settings(
        tmp_path,
        sync_incremental_lookback_days=3,
        sync_recovery_lookback_days=20,
    )
    assert incremental_settings.database_path is not None
    seed_movement(incremental_settings.database_path)
    current = datetime(2026, 7, 29, 15, tzinfo=timezone.utc)

    incremental = resolver(incremental_settings, current).resolve(command())
    assert incremental.start_date == date(2026, 7, 26)

    record_completed_sync(
        incremental_settings.database_path,
        status=SyncStatus.ERROR,
        request_id="configured-failure",
    )
    recovery = resolver(incremental_settings, current).resolve(command())
    assert recovery.start_date == date(2026, 7, 9)


def test_timezone_uses_america_sao_paulo_date(tmp_path: Path) -> None:
    policy = resolver(
        settings(tmp_path),
        datetime(2026, 8, 1, 1, 30, tzinfo=timezone.utc),
    )

    period = policy.resolve(command())

    assert period.policy_mode is SyncPolicyMode.INITIAL_LOAD
    assert period.start_date == date(2026, 7, 1)
    assert period.end_date == date(2026, 7, 31)
