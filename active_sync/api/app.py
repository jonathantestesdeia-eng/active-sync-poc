"""Fabrica da aplicacao FastAPI pronta para ambientes controlados."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from active_sync.config import ApplicationSettings
from active_sync.logger import configure_api_logging
from active_sync.storage import create_sync_backup
from active_sync.operation import (
    OperationalSyncPipeline,
    OperationalObservability,
    LoggingSyncNotifier,
    SyncCoordinator,
    SyncHistoryStore,
    SyncReprocessor,
    SyncScheduler,
    SchedulerConfigurationService,
    SchedulerConfigurationStore,
)

from .exceptions import register_exception_handlers
from .middleware import OriginValidationMiddleware, RequestContextMiddleware
from .routes import router
from .security import ApiKeyMiddleware


def create_app(settings: ApplicationSettings | None = None) -> FastAPI:
    """Cria uma aplicacao isolada, configuravel e substituivel em testes."""
    selected = settings or ApplicationSettings.from_env(validate_required=False)
    configure_api_logging(selected.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        selected.validate_required()
        application.state.settings = selected
        logger = logging.getLogger("active_sync.api")
        if selected.database_path is None:
            raise RuntimeError("Banco operacional nao configurado.")
        started_at = datetime.now(timezone.utc)
        history = SyncHistoryStore(selected.database_path)
        history.initialize()
        recovered_syncs = history.recover_interrupted(started_at)
        if recovered_syncs:
            logger.warning(
                "sync_recovery_completed",
                extra={
                    "recovered_syncs": recovered_syncs,
                    "finished_at": started_at,
                },
            )
        pipeline = OperationalSyncPipeline(selected, logger)
        notifier = LoggingSyncNotifier(logger)
        backup = create_sync_backup(selected, logger)
        coordinator = SyncCoordinator(
            pipeline,
            history,
            logger,
            profile=selected.processing_profile,
            notifier=notifier,
            backup=backup,
        )
        scheduler_store = SchedulerConfigurationStore(selected.database_path)
        scheduler_configuration = scheduler_store.initialize(selected.sync_schedule)
        effective_schedule = (
            (scheduler_configuration.run_time,)
            if scheduler_configuration.enabled
            and scheduler_configuration.run_time is not None
            else ()
        )
        scheduler = SyncScheduler(coordinator, effective_schedule, logger)
        scheduler_configuration_service = SchedulerConfigurationService(
            scheduler_store,
            scheduler,
        )
        observability = OperationalObservability(selected, history, started_at)
        reprocessor = SyncReprocessor(
            coordinator,
            history,
            selected.sync_work_dir / "imports",
            notifier,
        )
        application.state.sync_coordinator = coordinator
        application.state.sync_scheduler = scheduler
        application.state.scheduler_configuration = scheduler_configuration_service
        application.state.operational_observability = observability
        application.state.sync_reprocessor = reprocessor
        application.state.started_at = started_at
        scheduler.start()
        logger.info(
            "application_started",
            extra={
                "environment": selected.environment.value,
                "version": selected.version,
                "database": selected.database_engine,
                "profile": selected.processing_profile.value,
            },
        )
        try:
            yield
        finally:
            await scheduler.stop()
            await coordinator.wait_current()
            logger.info("application_stopped")

    application = FastAPI(
        title="Active Sync API",
        version=selected.version,
        description="API oficial de consulta do Active Sync para o SuperTrack.",
        lifespan=lifespan,
    )
    application.state.settings = selected
    register_exception_handlers(application)
    application.include_router(router)

    application.add_middleware(ApiKeyMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(selected.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(OriginValidationMiddleware)
    application.add_middleware(RequestContextMiddleware)
    return application


app = create_app()
