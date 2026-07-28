"""Composition root e injecao de dependencias da API."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from active_sync.config import ApplicationSettings
from active_sync.operation import (
    OperationalObservability,
    SyncCoordinator,
    SyncReprocessor,
    SchedulerConfigurationService,
)
from active_sync.persistence import DatabaseManager, MigrationManager
from active_sync.repository import PerformanceRepository, SuperTrackRepository
from active_sync.services import DashboardService, PerformanceService, SuperTrackService


def get_application_settings(request: Request) -> ApplicationSettings:
    """Retorna a configuracao validada no startup."""
    return request.app.state.settings


def get_sync_coordinator(request: Request) -> SyncCoordinator:
    """Retorna o coordenador operacional inicializado no lifespan."""
    return request.app.state.sync_coordinator


def get_operational_observability(request: Request) -> OperationalObservability:
    return request.app.state.operational_observability


def get_sync_reprocessor(request: Request) -> SyncReprocessor:
    return request.app.state.sync_reprocessor


def get_scheduler_configuration(
    request: Request,
) -> SchedulerConfigurationService:
    return request.app.state.scheduler_configuration


async def get_database(
    settings: ApplicationSettings = Depends(get_application_settings),
) -> AsyncIterator[DatabaseManager]:
    """Fornece uma conexao SQLite isolada por requisicao."""
    if settings.database_path is None:
        raise RuntimeError("Banco de dados nao configurado.")
    with DatabaseManager(settings.database_path) as database:
        MigrationManager(database).migrate()
        yield database


async def check_database_health(
    database: DatabaseManager = Depends(get_database),
) -> bool:
    """Confirma que a conexao aceita uma consulta minima."""
    database.execute("SELECT 1").fetchone()
    return True


def get_performance_repository(
    database: DatabaseManager = Depends(get_database),
) -> PerformanceRepository:
    """Monta a Repository sobre a conexao da requisicao."""
    return PerformanceRepository(database)


def get_performance_service(
    repository: PerformanceRepository = Depends(get_performance_repository),
) -> PerformanceService:
    """Fornece o servico de consultas de performance."""
    return PerformanceService(repository)


def get_supertrack_repository(
    database: DatabaseManager = Depends(get_database),
) -> SuperTrackRepository:
    return SuperTrackRepository(database)


def get_supertrack_service(
    repository: SuperTrackRepository = Depends(get_supertrack_repository),
) -> SuperTrackService:
    return SuperTrackService(repository)


def get_dashboard_service(
    repository: PerformanceRepository = Depends(get_performance_repository),
) -> DashboardService:
    """Fornece o servico de indicadores."""
    return DashboardService(repository)
