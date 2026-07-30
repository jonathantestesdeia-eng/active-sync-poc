from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from active_sync.config import AppEnvironment, ApplicationSettings
from active_sync.exceptions import (
    StorageConfigurationError,
    StorageDisabledError,
)
from active_sync.storage import (
    BestEffortDriveBackup,
    DisabledFileStorage,
    DisabledSyncBackup,
    GoogleDriveConfig,
    GoogleDriveStorage,
    create_sync_backup,
    create_file_storage,
)


def application_settings(**overrides) -> ApplicationSettings:
    values = {
        "environment": AppEnvironment.TEST,
        "api_key": "test-api-key-123456789",
        "allowed_origins": ("http://testserver",),
        "database_path": Path("test.sqlite3"),
        "version": "test",
        "build_date": "2026-07-29",
    }
    values.update(overrides)
    return ApplicationSettings(**values)


def test_external_storage_is_disabled_by_default(tmp_path: Path) -> None:
    storage = create_file_storage(
        application_settings(),
        logging.getLogger("test.storage"),
    )

    assert isinstance(storage, DisabledFileStorage)
    with pytest.raises(StorageDisabledError, match="desabilitado"):
        storage.store_file(tmp_path / "report.zip")


def test_google_drive_config_requires_folder_and_one_credential_source(
    tmp_path: Path,
) -> None:
    with pytest.raises(StorageConfigurationError, match="FOLDER_ID"):
        GoogleDriveConfig(folder_id="", credentials_json="{}").validate()

    with pytest.raises(StorageConfigurationError, match="exatamente uma"):
        GoogleDriveConfig(folder_id="folder").validate()

    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    with pytest.raises(StorageConfigurationError, match="exatamente uma"):
        GoogleDriveConfig(
            folder_id="folder",
            credentials_path=credentials,
            credentials_json="{}",
        ).validate()


def test_factory_prepares_google_drive_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connected = False

    def unexpected_connection(_credentials):
        nonlocal connected
        connected = True
        raise AssertionError("A fábrica não deve conectar ao Google Drive.")

    monkeypatch.setattr(
        GoogleDriveStorage,
        "_default_service_factory",
        staticmethod(unexpected_connection),
    )
    storage = create_file_storage(
        application_settings(
            google_drive_enabled=True,
            google_drive_folder_id="folder-id",
            google_drive_credentials_json='{"type":"authorized_user"}',
        ),
        logging.getLogger("test.storage"),
    )

    assert isinstance(storage, GoogleDriveStorage)
    assert connected is False


def test_google_credentials_are_not_exposed_in_settings_repr() -> None:
    settings = application_settings(
        google_drive_credentials_json='{"refresh_token":"sensitive"}'
    )

    assert "sensitive" not in repr(settings)


class FakeRequest:
    def __init__(self, payload) -> None:
        self.payload = payload

    def execute(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeDriveFiles:
    def __init__(self, folder_results: list[dict]) -> None:
        self.folder_results = list(folder_results)
        self.created_folders: list[dict] = []
        self.uploads: list[dict] = []

    def list(self, **_kwargs):
        return FakeRequest(self.folder_results.pop(0))

    def create(self, **kwargs):
        body = kwargs["body"]
        if body.get("mimeType"):
            self.created_folders.append(body)
            return FakeRequest(
                {"id": f"folder-{len(self.created_folders)}", "name": body["name"]}
            )
        self.uploads.append(body)
        return FakeRequest(
            {
                "id": f"file-{len(self.uploads)}",
                "name": body["name"],
                "webViewLink": "https://drive.example/file",
            }
        )


class FakeDrive:
    def __init__(self, files: FakeDriveFiles) -> None:
        self.resource = files

    def files(self) -> FakeDriveFiles:
        return self.resource


def drive_storage(fake_files: FakeDriveFiles) -> GoogleDriveStorage:
    storage = GoogleDriveStorage(
        GoogleDriveConfig(
            folder_id="root",
            credentials_json='{"type":"authorized_user"}',
        ),
        logging.getLogger("test.storage"),
    )
    storage._service = FakeDrive(fake_files)
    return storage


def test_successful_backup_creates_missing_year_month_hierarchy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "report.zip"
    source.write_bytes(b"PK-test")
    fake_files = FakeDriveFiles(
        [{"files": []}, {"files": []}, {"files": []}]
    )
    backup = BestEffortDriveBackup(
        drive_storage(fake_files),
        logging.getLogger("test.storage"),
    )

    result = backup.backup_files(
        (source,),
        completed_at=datetime(2026, 7, 29, 15, tzinfo=timezone.utc),
        request_id="request-1",
    )

    assert result.uploaded == 1
    assert result.failed == 0
    assert [folder["name"] for folder in fake_files.created_folders] == [
        "Active Sync",
        "2026",
        "07",
    ]
    assert fake_files.uploads == [
        {"name": "report.zip", "parents": ["folder-3"]}
    ]


def test_existing_google_drive_hierarchy_is_reused(tmp_path: Path) -> None:
    source = tmp_path / "report.zip"
    source.write_bytes(b"PK-test")
    fake_files = FakeDriveFiles(
        [
            {"files": [{"id": "active-sync"}]},
            {"files": [{"id": "year-2026"}]},
            {"files": [{"id": "month-07"}]},
        ]
    )
    backup = BestEffortDriveBackup(
        drive_storage(fake_files),
        logging.getLogger("test.storage"),
    )

    result = backup.backup_files(
        (source,),
        completed_at=datetime(2026, 7, 29, 15, tzinfo=timezone.utc),
        request_id="request-2",
    )

    assert result.uploaded == 1
    assert fake_files.created_folders == []
    assert fake_files.uploads[0]["parents"] == ["month-07"]


class FailingStorage:
    provider = "failing"

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.upload_called = False

    def ensure_directory(self, path: tuple[str, ...]) -> str:
        del path
        raise self.error

    def store_file(self, source: Path, **_kwargs):
        del source
        self.upload_called = True
        raise AssertionError("Upload não deveria ser iniciado.")


@pytest.mark.parametrize(
    "error",
    [
        StorageConfigurationError("token expirado"),
        ConnectionError("rede indisponível"),
    ],
    ids=["authentication", "network"],
)
def test_backup_failures_are_non_critical(tmp_path: Path, error: Exception) -> None:
    source = tmp_path / "report.zip"
    source.write_bytes(b"PK-test")
    storage = FailingStorage(error)
    backup = BestEffortDriveBackup(storage, logging.getLogger("test.storage"))

    result = backup.backup_files(
        (source,),
        completed_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        request_id="request-failure",
    )

    assert result.uploaded == 0
    assert result.failed == 1
    assert storage.upload_called is False


def test_disabled_backup_is_a_noop() -> None:
    backup = create_sync_backup(
        application_settings(google_drive_enabled=False),
        logging.getLogger("test.storage"),
    )

    assert isinstance(backup, DisabledSyncBackup)
    assert backup.backup_files(
        (Path("report.zip"),),
        completed_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        request_id="request-disabled",
    ).uploaded == 0


def test_invalid_enabled_configuration_degrades_to_disabled_backup() -> None:
    backup = create_sync_backup(
        application_settings(
            google_drive_enabled=True,
            google_drive_folder_id=None,
        ),
        logging.getLogger("test.storage"),
    )

    assert isinstance(backup, DisabledSyncBackup)
