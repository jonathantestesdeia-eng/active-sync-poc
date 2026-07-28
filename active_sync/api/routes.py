"""Rotas HTTP que consomem exclusivamente os Services."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, time as clock_time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status

from active_sync.config import ApplicationSettings
from active_sync.operation import (
    OperationalObservability,
    SyncAlreadyRunningError,
    SyncCoordinator,
    SyncHistoryEntry,
    SyncMode,
    SyncReprocessor,
    SyncValidationError,
    SchedulerConfigurationService,
)
from active_sync.services import (
    CategoryCount,
    DashboardService,
    PerformanceQuery,
    PerformanceService,
    SuperTrackService,
)

from .dependencies import (
    check_database_health,
    get_application_settings,
    get_dashboard_service,
    get_operational_observability,
    get_scheduler_configuration,
    get_performance_service,
    get_supertrack_service,
    get_sync_coordinator,
    get_sync_reprocessor,
)
from .schemas import (
    CategoryResponse,
    DatabaseHealthResponse,
    DashboardResponse,
    ErrorResponse,
    HealthResponse,
    InfoResponse,
    PerformanceResponse,
    SuperTrackInvoiceResponse,
    SuperTrackMovementResponse,
    SyncHistoryResponse,
    SyncPeriodRequest,
    SyncReprocessRequest,
    SyncRunRequest,
    SyncStartedResponse,
    SyncStatusResponse,
    SchedulerConfigurationRequest,
    SchedulerConfigurationResponse,
    SystemStatusResponse,
    StatisticsResponse,
    VersionResponse,
)


router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(
    observability: Annotated[
        OperationalObservability, Depends(get_operational_observability)
    ],
) -> HealthResponse:
    snapshot = observability.health()
    return HealthResponse(
        status=snapshot.status,
        database=snapshot.database,
        api=snapshot.api,
        storage=snapshot.storage,
        version=snapshot.version,
        timestamp=snapshot.timestamp,
    )


@router.get("/health/database", response_model=DatabaseHealthResponse, tags=["system"])
async def health_database(
    settings: Annotated[ApplicationSettings, Depends(get_application_settings)],
    healthy: Annotated[bool, Depends(check_database_health)],
) -> DatabaseHealthResponse:
    del healthy
    return DatabaseHealthResponse(status="ok", database=settings.database_engine)


@router.get("/health/version", response_model=VersionResponse, tags=["system"])
async def health_version(
    settings: Annotated[ApplicationSettings, Depends(get_application_settings)],
) -> VersionResponse:
    return VersionResponse(version=settings.version, build_date=settings.build_date)


@router.get("/info", response_model=InfoResponse, tags=["system"])
async def info(
    settings: Annotated[ApplicationSettings, Depends(get_application_settings)],
) -> InfoResponse:
    return InfoResponse(
        version=settings.version,
        environment=settings.environment.value,
        build_date=settings.build_date,
        database=settings.database_engine,
    )


def _sync_history_response(entry: SyncHistoryEntry) -> SyncHistoryResponse:
    summary = (
        f"Lidas {entry.records_read}; inseridas {entry.records_inserted}; "
        f"atualizadas {entry.records_updated}; ignoradas {entry.records_ignored}; "
        f"canceladas {entry.records_cancelled}."
    )
    return SyncHistoryResponse(
        id=entry.id,
        request_id=entry.request_id,
        sync_type=entry.mode.value,
        started_at=entry.started_at,
        finished_at=entry.finished_at,
        duration_ms=entry.duration_ms,
        status=entry.status.value,
        records_read=entry.records_read,
        records_inserted=entry.records_inserted,
        records_updated=entry.records_updated,
        records_ignored=entry.records_ignored,
        records_processed=entry.records_processed,
        errors=entry.errors,
        user=entry.user,
        origin=entry.origin.value,
        profile=entry.profile.value,
        start_date=entry.start_date,
        end_date=entry.end_date,
        source_files=list(entry.source_files),
        records_cancelled=entry.records_cancelled,
        message=entry.errors,
        warnings=list(entry.warnings),
        messages=list(entry.messages),
        summary=summary,
        reprocess_of_id=entry.reprocess_of_id,
    )


@router.get("/system/status", response_model=SystemStatusResponse, tags=["system"])
async def system_status(
    observability: Annotated[
        OperationalObservability, Depends(get_operational_observability)
    ],
) -> SystemStatusResponse:
    snapshot = observability.system_status()
    return SystemStatusResponse(
        api=snapshot.api,
        database=snapshot.database,
        active_profile=snapshot.active_profile,
        total_records=snapshot.total_records,
        last_sync=(
            _sync_history_response(snapshot.last_sync)
            if snapshot.last_sync is not None
            else None
        ),
        version=snapshot.version,
        environment=snapshot.environment,
        uptime_seconds=snapshot.uptime_seconds,
        health=snapshot.health,
    )


@router.get("/statistics", response_model=StatisticsResponse, tags=["system"])
async def statistics(
    observability: Annotated[
        OperationalObservability, Depends(get_operational_observability)
    ],
) -> StatisticsResponse:
    snapshot = observability.statistics()
    return StatisticsResponse(
        total_movements=snapshot.total_movements,
        total_returns=snapshot.total_returns,
        total_cancelled=snapshot.total_cancelled,
        first_sync_at=snapshot.first_sync_at,
        last_sync_at=snapshot.last_sync_at,
        sync_count=snapshot.sync_count,
        failure_count=snapshot.failure_count,
        average_duration_ms=snapshot.average_duration_ms,
        maximum_duration_ms=snapshot.maximum_duration_ms,
        minimum_duration_ms=snapshot.minimum_duration_ms,
        seconds_since_last_execution=snapshot.seconds_since_last_execution,
    )


async def _start_sync(
    coordinator: SyncCoordinator,
    mode: SyncMode,
    user: str | None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> SyncStartedResponse:
    try:
        entry = await coordinator.start(
            mode,
            start_date=start_date,
            end_date=end_date,
            user=user or "api-key",
        )
    except SyncAlreadyRunningError as error:
        raise HTTPException(
            status_code=409,
            detail="J\u00e1 existe uma sincroniza\u00e7\u00e3o em execu\u00e7\u00e3o.",
        ) from error
    except SyncValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return SyncStartedResponse(
        status=entry.status.value,
        request_id=entry.request_id,
        started_at=entry.started_at,
        sync_type=entry.mode.value,
    )


@router.post("/sync/run", response_model=SyncStartedResponse, status_code=202, tags=["sync"])
async def run_sync(
    payload: SyncRunRequest,
    coordinator: Annotated[SyncCoordinator, Depends(get_sync_coordinator)],
    user: Annotated[str | None, Header(alias="X-User")] = None,
) -> SyncStartedResponse:
    return await _start_sync(coordinator, SyncMode(payload.mode), user)


@router.post("/sync", response_model=SyncStartedResponse, status_code=202, tags=["sync"])
async def run_default_sync(
    coordinator: Annotated[SyncCoordinator, Depends(get_sync_coordinator)],
    user: Annotated[str | None, Header(alias="X-User")] = None,
) -> SyncStartedResponse:
    """Inicia a sincronização incremental pelo mesmo coordenador operacional."""
    return await _start_sync(coordinator, SyncMode.INCREMENTAL, user)


@router.post("/sync/run-period", response_model=SyncStartedResponse, status_code=202, tags=["sync"])
async def run_sync_period(
    payload: SyncPeriodRequest,
    coordinator: Annotated[SyncCoordinator, Depends(get_sync_coordinator)],
    user: Annotated[str | None, Header(alias="X-User")] = None,
) -> SyncStartedResponse:
    return await _start_sync(
        coordinator,
        SyncMode.PERIOD,
        user,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )


@router.post(
    "/sync/reprocess",
    response_model=SyncStartedResponse,
    status_code=202,
    tags=["sync"],
)
async def reprocess_sync(
    payload: SyncReprocessRequest,
    reprocessor: Annotated[SyncReprocessor, Depends(get_sync_reprocessor)],
    user: Annotated[str | None, Header(alias="X-User")] = None,
) -> SyncStartedResponse:
    try:
        selected_user = user or "api-key"
        if payload.start_date is not None and payload.end_date is not None:
            entry = await reprocessor.period(
                payload.start_date,
                payload.end_date,
                user=selected_user,
            )
        elif payload.file is not None:
            entry = await reprocessor.file(payload.file, user=selected_user)
        else:
            entry = await reprocessor.sync_id(
                int(payload.sync_id),
                user=selected_user,
            )
    except SyncAlreadyRunningError as error:
        raise HTTPException(
            status_code=409,
            detail="Já existe uma sincronização em execução.",
        ) from error
    except SyncValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return SyncStartedResponse(
        status=entry.status.value,
        request_id=entry.request_id,
        started_at=entry.started_at,
        sync_type=entry.mode.value,
    )


@router.get("/sync/history", response_model=list[SyncHistoryResponse], tags=["sync"])
async def sync_history(
    coordinator: Annotated[SyncCoordinator, Depends(get_sync_coordinator)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SyncHistoryResponse]:
    return [_sync_history_response(entry) for entry in coordinator.list_history(limit, offset)]


@router.get("/sync/history/{entry_id}", response_model=SyncHistoryResponse, tags=["sync"])
async def sync_history_detail(
    coordinator: Annotated[SyncCoordinator, Depends(get_sync_coordinator)],
    entry_id: Annotated[int, Path(ge=1)],
) -> SyncHistoryResponse:
    entry = coordinator.get_history(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Execu\u00e7\u00e3o n\u00e3o encontrada.")
    return _sync_history_response(entry)


@router.get("/status", response_model=SyncStatusResponse, tags=["sync"])
@router.get("/sync/status", response_model=SyncStatusResponse, tags=["sync"])
async def sync_status(
    coordinator: Annotated[SyncCoordinator, Depends(get_sync_coordinator)],
) -> SyncStatusResponse:
    current = coordinator.status()
    latest = current["latest"]
    return SyncStatusResponse(
        running=bool(current["running"]),
        current=_sync_history_response(current["current"]) if current["current"] else None,
        last_execution=_sync_history_response(latest) if latest else None,
        next_scheduled_at=current["next_scheduled_at"],
        last_duration_ms=latest.duration_ms if latest else None,
        records_processed=latest.records_processed if latest else 0,
        final_status=latest.status.value if latest else None,
    )


def _scheduler_configuration_response(
    service: SchedulerConfigurationService,
) -> SchedulerConfigurationResponse:
    configuration = service.get()
    return SchedulerConfigurationResponse(
        enabled=configuration.enabled,
        time=(
            configuration.run_time.strftime("%H:%M")
            if configuration.run_time is not None
            else None
        ),
        updated_at=configuration.updated_at,
        next_scheduled_at=service.next_run(),
    )


@router.get(
    "/scheduler/config",
    response_model=SchedulerConfigurationResponse,
    tags=["scheduler"],
)
async def get_scheduler_config(
    service: Annotated[
        SchedulerConfigurationService, Depends(get_scheduler_configuration)
    ],
) -> SchedulerConfigurationResponse:
    return _scheduler_configuration_response(service)


@router.put(
    "/scheduler/config",
    response_model=SchedulerConfigurationResponse,
    tags=["scheduler"],
)
async def update_scheduler_config(
    payload: SchedulerConfigurationRequest,
    service: Annotated[
        SchedulerConfigurationService, Depends(get_scheduler_configuration)
    ],
) -> SchedulerConfigurationResponse:
    selected_time = (
        clock_time.fromisoformat(payload.time)
        if payload.time is not None
        else None
    )
    service.save(payload.enabled, selected_time)
    return _scheduler_configuration_response(service)


@router.get(
    "/performance",
    response_model=list[PerformanceResponse],
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["performance"],
)
async def list_performance(
    service: Annotated[PerformanceService, Depends(get_performance_service)],
    transportadora: str | None = None,
    uf_destino: str | None = None,
    cidade_destino: str | None = None,
    prazo: str | None = None,
    situacao: str | None = None,
    periodo_inicio: date | None = None,
    periodo_fim: date | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    order_by: str = "Nota Fiscal",
    descending: bool = False,
) -> list[PerformanceResponse]:
    query = PerformanceQuery(
        transportadora=transportadora,
        uf_destino=uf_destino,
        cidade_destino=cidade_destino,
        prazo=prazo,
        situacao=situacao,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        limit=limit,
        offset=offset,
        order_by=order_by,
        descending=descending,
    )
    return [PerformanceResponse.from_domain(record) for record in service.listar(query)]


@router.get(
    "/performance/{nota_fiscal}",
    response_model=list[PerformanceResponse],
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["performance"],
)
async def get_performance_by_invoice(
    service: Annotated[PerformanceService, Depends(get_performance_service)],
    nota_fiscal: Annotated[str, Path(min_length=1)],
) -> list[PerformanceResponse]:
    records = service.buscar_nf(nota_fiscal)
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota Fiscal não encontrada.",
        )
    return [PerformanceResponse.from_domain(record) for record in records]


@router.get(
    "/tracking/{nota_fiscal}",
    response_model=SuperTrackInvoiceResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["tracking"],
)
async def get_tracking_by_invoice(
    service: Annotated[SuperTrackService, Depends(get_supertrack_service)],
    nota_fiscal: Annotated[str, Path(min_length=1)],
) -> SuperTrackInvoiceResponse:
    movements = service.buscar_nf(nota_fiscal)
    if not movements:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota Fiscal não encontrada na base operacional.",
        )
    return SuperTrackInvoiceResponse(
        notaFiscal=nota_fiscal,
        total=len(movements),
        movimentos=[
            SuperTrackMovementResponse.from_domain(movement)
            for movement in movements
        ],
    )


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    responses={503: {"model": ErrorResponse}},
    tags=["dashboard"],
)
async def dashboard(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardResponse:
    return DashboardResponse(
        total_registros=service.total_registros(),
        total_atrasadas=service.total_atrasadas(),
        total_em_aberto=service.total_em_aberto(),
        total_entregues=service.total_entregues(),
        total_devolvidas=service.total_devolvidas(),
        percentual_atraso=service.percentual_atraso(),
        percentual_entregues=service.percentual_entregues(),
        percentual_devolvidas=service.percentual_devolvidas(),
    )


def _category_response(items: Iterable[CategoryCount]) -> list[CategoryResponse]:
    return [
        CategoryResponse(label=item.label, count=item.count)
        for item in items
    ]


@router.get(
    "/dashboard/transportadoras",
    response_model=list[CategoryResponse],
    responses={503: {"model": ErrorResponse}},
    tags=["dashboard"],
)
async def dashboard_transportadoras(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> list[CategoryResponse]:
    return _category_response(service.transportadoras())


@router.get(
    "/dashboard/ufs",
    response_model=list[CategoryResponse],
    responses={503: {"model": ErrorResponse}},
    tags=["dashboard"],
)
async def dashboard_ufs(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> list[CategoryResponse]:
    return _category_response(service.ufs())


@router.get(
    "/dashboard/cidades",
    response_model=list[CategoryResponse],
    responses={503: {"model": ErrorResponse}},
    tags=["dashboard"],
)
async def dashboard_cidades(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> list[CategoryResponse]:
    return _category_response(service.cidades())
