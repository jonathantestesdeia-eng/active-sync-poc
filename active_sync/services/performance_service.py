"""Serviço de coordenação das consultas de Performance Entrega."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, TypeVar

from active_sync.repository import (
    PerformanceEntrega,
    PerformanceFilters,
    PerformanceRepository,
    RepositoryError,
)

from .exceptions import ServiceError


_Result = TypeVar("_Result")


@dataclass(frozen=True, slots=True)
class PerformanceQuery:
    """DTO de filtros, paginação e ordenação exposto pelos Services."""

    transportadora: str | None = None
    uf_destino: str | None = None
    cidade_destino: str | None = None
    prazo: str | None = None
    situacao: str | None = None
    periodo_inicio: date | str | None = None
    periodo_fim: date | str | None = None
    limit: int | None = None
    offset: int = 0
    order_by: str = "Nota Fiscal"
    descending: bool = False

    def repository_filters(self) -> PerformanceFilters:
        """Converte o DTO público para o contrato interno da Repository."""
        return PerformanceFilters(
            transportadora=self.transportadora,
            uf_destino=self.uf_destino,
            cidade_destino=self.cidade_destino,
            prazo=self.prazo,
            situacao=self.situacao,
            periodo_inicio=self.periodo_inicio,
            periodo_fim=self.periodo_fim,
        )


class PerformanceService:
    """Coordena consultas sem conhecer SQL ou o mecanismo de persistência."""

    def __init__(self, repository: PerformanceRepository) -> None:
        self.repository = repository

    def listar(
        self,
        query: PerformanceQuery | None = None,
    ) -> list[PerformanceEntrega]:
        """Lista registros conforme o DTO de consulta."""
        request = query or PerformanceQuery()
        return self._call(
            self.repository.listar,
            request.repository_filters(),
            limit=request.limit,
            offset=request.offset,
            order_by=request.order_by,
            descending=request.descending,
        )

    def buscar_nf(self, nota_fiscal: str) -> list[PerformanceEntrega]:
        """Busca uma Nota Fiscal por correspondência exata."""
        return self._call(self.repository.buscar_por_nf, nota_fiscal)

    def buscar_transportadora(
        self,
        transportadora: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PerformanceEntrega]:
        """Busca uma transportadora com paginação opcional."""
        return self._call(
            self.repository.buscar_por_transportadora,
            transportadora,
            limit=limit,
            offset=offset,
        )

    def buscar_periodo(
        self,
        periodo_inicio: date | str,
        periodo_fim: date | str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PerformanceEntrega]:
        """Busca um intervalo inclusivo de Saída."""
        return self._call(
            self.repository.buscar_por_periodo,
            periodo_inicio,
            periodo_fim,
            limit=limit,
            offset=offset,
        )

    def buscar_atrasadas(self) -> list[PerformanceEntrega]:
        """Retorna entregas atrasadas."""
        return self._call(self.repository.buscar_atrasadas)

    def buscar_em_aberto(self) -> list[PerformanceEntrega]:
        """Retorna entregas em aberto."""
        return self._call(self.repository.buscar_em_aberto)

    def buscar_devolvidas(self) -> list[PerformanceEntrega]:
        """Retorna registros de devolução."""
        return self._call(self.repository.buscar_devolvidas)

    def contar(self, query: PerformanceQuery | None = None) -> int:
        """Conta todos os registros ou somente os filtrados."""
        filters = query.repository_filters() if query is not None else None
        return self._call(self.repository.contar, filters)

    def _call(
        self,
        operation: Callable[..., _Result],
        *args: object,
        **kwargs: object,
    ) -> _Result:
        try:
            return operation(*args, **kwargs)
        except RepositoryError as error:
            raise ServiceError("Não foi possível concluir a consulta.") from error
