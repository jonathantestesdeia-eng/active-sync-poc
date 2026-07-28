from __future__ import annotations

import pytest
from datetime import date, time

from active_sync.config import AppEnvironment, ApplicationSettings, Settings
from active_sync.exceptions import ConfigError


def test_missing_user_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("ACTIVE_USER", raising=False)
    monkeypatch.setenv("ACTIVE_PASSWORD", "segredo-de-teste")

    with pytest.raises(ConfigError, match="ACTIVE_USER"):
        Settings.from_env(tmp_path / "inexistente.env")


def test_minimum_login_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("ACTIVE_USER", "usuario-de-teste")
    monkeypatch.setenv("ACTIVE_PASSWORD", "segredo-de-teste")

    settings = Settings.from_env(tmp_path / "inexistente.env")

    assert settings.user == "usuario-de-teste"
    assert settings.password == "segredo-de-teste"
    assert settings.base_url == "https://activeonsupply.com.br"


def test_application_settings_separate_environments_and_process_precedence(tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "APP_ENV=test\nACTIVE_SYNC_VERSION=base\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.test").write_text(
        "ACTIVE_SYNC_VERSION=scoped\nACTIVE_SYNC_BUILD_DATE=2026-07-22\n",
        encoding="utf-8",
    )
    settings = ApplicationSettings.from_env(
        project_root=tmp_path,
        environ={
            "ACTIVE_SYNC_API_KEY": "test-api-key-123456789",
            "ACTIVE_SYNC_ALLOWED_ORIGINS": "http://localhost:5173,https://app.example",
            "ACTIVE_SYNC_DATABASE_PATH": "test.sqlite3",
            "ACTIVE_SYNC_VERSION": "process",
        },
    )
    assert settings.environment is AppEnvironment.TEST
    assert settings.version == "process"
    assert settings.build_date == "2026-07-22"
    assert settings.allowed_origins == ("http://localhost:5173", "https://app.example")
    assert settings.debug is False


def test_application_settings_validate_required_values(tmp_path) -> None:
    with pytest.raises(ConfigError, match="ACTIVE_SYNC_API_KEY"):
        ApplicationSettings.from_env(project_root=tmp_path, environ={"APP_ENV": "test"})

    with pytest.raises(ConfigError, match="ao menos 16"):
        ApplicationSettings.from_env(
            project_root=tmp_path,
            environ={
                "APP_ENV": "production",
                "ACTIVE_SYNC_API_KEY": "curta",
                "ACTIVE_SYNC_ALLOWED_ORIGINS": "https://app.example",
                "ACTIVE_SYNC_DATABASE_PATH": "prod.sqlite3",
                "ACTIVE_SYNC_BUILD_DATE": "2026-07-22",
            },
        )


def test_application_settings_reject_unknown_environment_and_wildcard(tmp_path) -> None:
    with pytest.raises(ConfigError, match="APP_ENV"):
        ApplicationSettings.from_env(project_root=tmp_path, environ={"APP_ENV": "staging"})

    with pytest.raises(ConfigError, match="curinga"):
        ApplicationSettings.from_env(
            project_root=tmp_path,
            environ={
                "APP_ENV": "production",
                "ACTIVE_SYNC_API_KEY": "production-key-123456789",
                "ACTIVE_SYNC_ALLOWED_ORIGINS": "*",
                "ACTIVE_SYNC_DATABASE_PATH": "prod.sqlite3",
                "ACTIVE_SYNC_BUILD_DATE": "2026-07-22",
            },
        )


def test_sync_schedule_and_operational_settings_are_loaded_from_environment(tmp_path) -> None:
    settings = ApplicationSettings.from_env(
        project_root=tmp_path,
        environ={
            "APP_ENV": "test",
            "ACTIVE_SYNC_API_KEY": "test-api-key-123456789",
            "ACTIVE_SYNC_ALLOWED_ORIGINS": "http://testserver",
            "ACTIVE_SYNC_DATABASE_PATH": "test.sqlite3",
            "ACTIVE_SYNC_SCHEDULE": "18:00,08:00,12:00",
            "ACTIVE_SYNC_FULL_START_DATE": "2026-01-01",
            "ACTIVE_SYNC_INCREMENTAL_LOOKBACK_DAYS": "3",
            "ACTIVE_SYNC_WORK_DIR": "runtime-test",
        },
    )
    assert settings.sync_schedule == (time(8), time(12), time(18))
    assert settings.sync_full_start_date == date(2026, 1, 1)
    assert settings.sync_incremental_lookback_days == 3


def test_invalid_sync_schedule_is_rejected(tmp_path) -> None:
    with pytest.raises(ConfigError, match="HH:MM"):
        ApplicationSettings.from_env(
            project_root=tmp_path,
            environ={
                "APP_ENV": "test",
                "ACTIVE_SYNC_API_KEY": "test-api-key-123456789",
                "ACTIVE_SYNC_ALLOWED_ORIGINS": "http://testserver",
                "ACTIVE_SYNC_DATABASE_PATH": "test.sqlite3",
                "ACTIVE_SYNC_SCHEDULE": "8 horas",
            },
        )
