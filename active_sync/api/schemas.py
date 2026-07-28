"""Contratos HTTP da API Active Sync."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiSchema(BaseModel):
    """Configuração comum dos schemas públicos."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiSchema):
    status: Literal["ok", "degraded"]
    database: str
    api: str
    storage: str
    version: str
    timestamp: datetime


class DatabaseHealthResponse(ApiSchema):
    status: Literal["ok"]
    database: str


class VersionResponse(ApiSchema):
    version: str
    build_date: str


class InfoResponse(ApiSchema):
    version: str
    environment: str
    build_date: str
    database: str


class SyncRunRequest(ApiSchema):
    mode: Literal["INCREMENTAL", "FULL"] = "INCREMENTAL"


class SyncPeriodRequest(ApiSchema):
    start_date: date
    end_date: date


class SyncReprocessRequest(ApiSchema):
    start_date: date | None = None
    end_date: date | None = None
    file: str | None = Field(default=None, min_length=1)
    sync_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_selector(self) -> SyncReprocessRequest:
        has_period = self.start_date is not None or self.end_date is not None
        if has_period and (self.start_date is None or self.end_date is None):
            raise ValueError("Data inicial e final são obrigatórias para o período.")
        selectors = int(has_period) + int(self.file is not None) + int(self.sync_id is not None)
        if selectors != 1:
            raise ValueError("Informe apenas período, arquivo ou sync_id.")
        return self


class SyncStartedResponse(ApiSchema):
    status: str
    request_id: str
    started_at: datetime
    sync_type: str


class SyncHistoryResponse(ApiSchema):
    id: int
    request_id: str
    sync_type: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: float | None
    status: str
    records_read: int
    records_inserted: int
    records_updated: int
    records_ignored: int
    records_processed: int
    errors: str | None
    user: str
    origin: str
    profile: str
    start_date: date | None
    end_date: date | None
    source_files: list[str]
    records_cancelled: int
    message: str | None
    warnings: list[str]
    messages: list[str]
    summary: str
    reprocess_of_id: int | None


class SyncStatusResponse(ApiSchema):
    running: bool
    current: SyncHistoryResponse | None
    last_execution: SyncHistoryResponse | None
    next_scheduled_at: datetime | None
    last_duration_ms: float | None
    records_processed: int
    final_status: str | None


class SchedulerConfigurationRequest(ApiSchema):
    enabled: bool
    time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def validate_enabled_time(self) -> SchedulerConfigurationRequest:
        if self.enabled and self.time is None:
            raise ValueError("Informe um horário válido.")
        return self


class SchedulerConfigurationResponse(ApiSchema):
    enabled: bool
    frequency: Literal["DAILY"] = "DAILY"
    time: str | None
    timezone: Literal["America/Sao_Paulo"] = "America/Sao_Paulo"
    timezone_label: str = "America/Sao_Paulo (GMT-3)"
    updated_at: datetime
    next_scheduled_at: datetime | None


class SystemStatusResponse(ApiSchema):
    api: str
    database: str
    active_profile: str
    total_records: int = Field(ge=0)
    last_sync: SyncHistoryResponse | None
    version: str
    environment: str
    uptime_seconds: float = Field(ge=0)
    health: str


class StatisticsResponse(ApiSchema):
    total_movements: int = Field(ge=0)
    total_returns: int = Field(ge=0)
    total_cancelled: int = Field(ge=0)
    first_sync_at: datetime | None
    last_sync_at: datetime | None
    sync_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    average_duration_ms: float | None
    maximum_duration_ms: float | None
    minimum_duration_ms: float | None
    seconds_since_last_execution: float | None


class CategoryResponse(ApiSchema):
    label: str
    count: int = Field(ge=0)


class DashboardResponse(ApiSchema):
    total_registros: int = Field(ge=0)
    total_atrasadas: int = Field(ge=0)
    total_em_aberto: int = Field(ge=0)
    total_entregues: int = Field(ge=0)
    total_devolvidas: int = Field(ge=0)
    percentual_atraso: float = Field(ge=0)
    percentual_entregues: float = Field(ge=0)
    percentual_devolvidas: float = Field(ge=0)


class PerformanceResponse(ApiSchema):
    cnpj: str | None = Field(validation_alias="CNPJ")
    destinatario: str | None = Field(validation_alias="Destinatário")
    cidade_origem: str | None = Field(validation_alias="Cidade Origem")
    cidade_destino: str | None = Field(validation_alias="Cidade Destino")
    uf_destino: str | None = Field(validation_alias="UF Destino")
    nota_fiscal: str | None = Field(validation_alias="Nota Fiscal")
    valor_frete: float | None = Field(validation_alias="Valor Frete")
    saida: date | None = Field(validation_alias="Saída")
    previsao: date | None = Field(validation_alias="Previsão")
    entrega: date | None = Field(validation_alias="Entrega")
    transportadora: str | None = Field(validation_alias="Transportadora")
    flag_devolucao_nf: bool = Field(validation_alias="Flag Devolução NF")
    tipo_cte: str | None = Field(validation_alias="Tipo CTe")
    cte_devolucao: str | None = Field(validation_alias="CTe Devolução")
    codigo_cliente: str | None = Field(validation_alias="Código cliente")
    prazo: str = Field(validation_alias="Prazo")
    data: str | None = Field(validation_alias="Data")
    ano: int | None = Field(validation_alias="Ano")
    prazo2: str = Field(validation_alias="Prazo2")
    data3: str | None = Field(validation_alias="Data3")
    ano4: int | None = Field(validation_alias="Ano4")
    situacao: str = Field(validation_alias="Situação")

    @classmethod
    def from_domain(cls, record: Any) -> PerformanceResponse:
        """Converte o modelo imutável sem expor sua implementação."""
        as_dict = getattr(record, "as_dict", None)
        if not callable(as_dict):
            raise TypeError("O resultado do Service não é um registro válido.")
        return cls.model_validate(as_dict())


class SuperTrackMovementResponse(ApiSchema):
    movementId: str
    notaFiscal: str
    cte: str
    serieCte: str
    chaveCte: str | None
    serieNf: str | None
    pedido: str | None
    tipoCte: str | None
    transportadora: str | None
    remetente: str | None
    destinatario: str | None
    cnpjDestinatario: str | None
    cidadeOrigem: str | None
    cidadeDestino: str | None
    ufDestino: str | None
    emissao: date | None
    saida: date | None
    previsao: date | None
    entrega: date | None
    situacao: str
    observacao: str | None
    valorFrete: float | None
    dataAtualizacao: date | None

    @classmethod
    def from_domain(cls, movement: Any) -> SuperTrackMovementResponse:
        return cls(
            movementId=movement.movement_id,
            notaFiscal=movement.nota_fiscal,
            cte=movement.cte,
            serieCte=movement.serie_cte,
            chaveCte=movement.chave_cte,
            serieNf=movement.serie_nf,
            pedido=movement.pedido,
            tipoCte=movement.tipo_cte,
            transportadora=movement.transportadora,
            remetente=movement.remetente,
            destinatario=movement.destinatario,
            cnpjDestinatario=movement.cnpj_destinatario,
            cidadeOrigem=movement.cidade_origem,
            cidadeDestino=movement.cidade_destino,
            ufDestino=movement.uf_destino,
            emissao=movement.emissao,
            saida=movement.saida,
            previsao=movement.previsao,
            entrega=movement.entrega,
            situacao=movement.situacao,
            observacao=movement.observacao,
            valorFrete=movement.valor_frete,
            dataAtualizacao=movement.data_atualizacao,
        )


class SuperTrackInvoiceResponse(ApiSchema):
    success: Literal[True] = True
    notaFiscal: str
    total: int = Field(ge=1)
    movimentos: list[SuperTrackMovementResponse]


class ErrorDetail(ApiSchema):
    code: str
    message: str
    request_id: str | None


class ErrorResponse(ApiSchema):
    error: ErrorDetail
