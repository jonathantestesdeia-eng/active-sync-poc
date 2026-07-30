"""Orquestrador unico que reutiliza o pipeline homologado do Active Sync."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
from time import monotonic
from typing import Callable

import pandas as pd

from active_sync.auth import login, select_company_context
from active_sync.client import ActiveClient
from active_sync.config import ApplicationSettings, Settings
from active_sync.downloader import download_zip
from active_sync.excel_reader import read_excel_dataframe
from active_sync.extractor import extract_zip
from active_sync.persistence import DatabaseManager, MigrationManager
from active_sync.report_grid import poll_current_report
from active_sync.reports import ReportWindow, request_report

from .models import SyncCommand, SyncMode, SyncResult, SyncValidationError
from .profiles import get_processing_profile
from .sync_policy import SYNC_TIMEZONE, SyncPeriodResolver


MAX_WINDOW_DAYS = 7


class OperationalSyncPipeline:
    """Executa todos os modos pela mesma sequencia de componentes existentes."""

    def __init__(
        self,
        application_settings: ApplicationSettings,
        logger: logging.Logger,
        *,
        today: Callable[[], date] | None = None,
    ) -> None:
        self.application_settings = application_settings
        self.logger = logger
        self.today = today or date.today
        resolver_now = (
            lambda: datetime.combine(self.today(), time.min, tzinfo=SYNC_TIMEZONE)
            if today is not None
            else None
        )
        self.period_resolver = SyncPeriodResolver(
            application_settings,
            logger,
            now=resolver_now,
        )
        self.profile = get_processing_profile(
            application_settings.processing_profile
        )

    def execute(self, command: SyncCommand) -> SyncResult:
        if command.mode is SyncMode.FILE:
            return self._execute_file(command)
        start_date, end_date = self._resolve_dates(command)
        client_register = self._load_client_register()
        total = SyncResult()
        self.logger.info(
            "sync_pipeline_started",
            extra={
                "profile": self.profile.name.value,
                "sync_mode": command.mode.value,
                "request_id": command.request_id,
            },
        )
        active_settings = Settings.from_env()
        active_settings.validate_context()
        with ActiveClient(active_settings) as client:
            login_result = login(client, self.logger)
            select_company_context(client, login_result, self.logger)
            for window in self._windows(start_date, end_date):
                total += self._execute_window(
                    client,
                    window,
                    client_register,
                    command.request_id,
                    command.mode,
                )
        if command.mode is SyncMode.FULL:
            self.logger.info(
                "sync_profile_full_consolidated",
                extra={
                    "profile": self.profile.name.value,
                    "sync_mode": command.mode.value,
                    "request_id": command.request_id,
                    "movements_removed_by_absence": 0,
                    "policy": "preserve_absent_movements",
                },
            )
        return total

    def _execute_file(self, command: SyncCommand) -> SyncResult:
        """Reprocessa Excel previamente armazenado usando o mesmo perfil homologado."""
        source_file = command.source_file
        if source_file is None:
            raise SyncValidationError("Arquivo obrigatório para reprocessamento.")
        if source_file.suffix.casefold() != ".xlsx" or not source_file.is_file():
            raise SyncValidationError(f"Arquivo de reprocessamento inválido: {source_file.name}")
        started_at = monotonic()
        raw, _, _ = read_excel_dataframe(source_file)
        client_register = self._load_client_register()
        batch = self.profile.process(
            raw,
            logger=self.logger,
            client_register=client_register,
        )
        with DatabaseManager(self._database_path()) as database:
            MigrationManager(database).migrate()
            merge = self.profile.persist(
                batch,
                database,
                request_id=command.request_id,
            )
        result = SyncResult(
            records_read=len(raw),
            records_inserted=merge.inserted,
            records_updated=merge.updated,
            records_ignored=batch.duplicates_removed + merge.ignored,
            records_cancelled=batch.cancelled_removed,
            source_files=(source_file.name,),
            messages=("Arquivo reprocessado pelo pipeline homologado.",),
        )
        self.logger.info(
            "sync_profile_file_completed",
            extra={
                "request_id": command.request_id,
                "profile": self.profile.name.value,
                "sync_mode": command.mode.value,
                "file": source_file.name,
                "records_read": result.records_read,
                "records_inserted": result.records_inserted,
                "records_updated": result.records_updated,
                "records_ignored": result.records_ignored,
                "records_cancelled": result.records_cancelled,
                "duration_ms": round((monotonic() - started_at) * 1000, 3),
            },
        )
        return result

    def _resolve_dates(self, command: SyncCommand) -> tuple[date, date]:
        resolved = self.period_resolver.resolve(command)
        return resolved.start_date, resolved.end_date

    @staticmethod
    def _windows(start_date: date, end_date: date) -> tuple[ReportWindow, ...]:
        windows: list[ReportWindow] = []
        cursor = start_date
        while cursor <= end_date:
            window_end = min(cursor + timedelta(days=MAX_WINDOW_DAYS - 1), end_date)
            windows.append(ReportWindow(date_from=cursor, date_to=window_end))
            cursor = window_end + timedelta(days=1)
        return tuple(windows)

    def _load_client_register(self) -> pd.DataFrame | None:
        path = self.application_settings.sync_client_register_path
        if path is None:
            return None
        if not path.exists():
            raise SyncValidationError(f"Base de clientes nao encontrada: {path}")
        return pd.read_excel(
            path,
            sheet_name=self.application_settings.sync_client_register_sheet or 0,
            dtype=object,
            engine="openpyxl",
        )

    def _execute_window(
        self,
        client: ActiveClient,
        window: ReportWindow,
        client_register: pd.DataFrame | None,
        request_id: str,
        mode: SyncMode,
    ) -> SyncResult:
        started_at = monotonic()
        request_result = request_report(client, window, self.logger)
        report_row = poll_current_report(client, request_result.local_before, self.logger)
        work_dir = self.application_settings.sync_work_dir
        download = download_zip(
            client,
            report_row.download_url or "",
            work_dir / "downloads",
            self.logger,
            keep_files=False,
        )
        extraction = extract_zip(
            download.path,
            work_dir / "extracted",
            self.logger,
            keep_files=False,
        )
        raw, _, _ = read_excel_dataframe(extraction.excel_path)
        batch = self.profile.process(
            raw,
            logger=self.logger,
            client_register=client_register,
        )
        database_path = self._database_path()
        with DatabaseManager(database_path) as database:
            MigrationManager(database).migrate()
            merge = self.profile.persist(
                batch,
                database,
                request_id=request_id,
            )
        ignored = batch.duplicates_removed + merge.ignored
        self.logger.info(
            "sync_profile_window_completed",
            extra={
                "profile": self.profile.name.value,
                "sync_mode": mode.value,
                "request_id": request_id,
                "total_extraido": batch.extracted,
                "total_cancelados_removidos": batch.cancelled_removed,
                "total_duplicidades_removidas": batch.duplicates_removed,
                "total_movimentos_preservados": batch.movements_preserved,
                "total_devolucoes_preservadas": batch.returns_preserved,
                "total_nfs_unicas": batch.unique_invoices,
                "total_ctes_unicos": batch.unique_ctes,
                "total_nfs_com_multiplos_ctes": batch.invoices_with_multiple_ctes,
                "duration_ms": round((monotonic() - started_at) * 1000, 3),
            },
        )
        return SyncResult(
            records_read=len(raw),
            records_inserted=merge.inserted,
            records_updated=merge.updated,
            records_ignored=ignored,
            records_cancelled=batch.cancelled_removed,
            source_files=(extraction.excel_path.name,),
            period_start=window.date_from,
            period_end=window.date_to,
            backup_files=(download.path,),
        )

    def _database_path(self):
        database_path = self.application_settings.database_path
        if database_path is None:
            raise SyncValidationError("Banco operacional nao configurado.")
        return database_path
