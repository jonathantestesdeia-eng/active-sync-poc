"""Indicadores de acompanhamento consumíveis pelo SuperTrack."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, TypeVar

from active_sync.repository import (
    PerformanceFilters,
    PerformanceRepository,
    RepositoryError,
)

from .exceptions import DashboardError


_Result = TypeVar("_Result")


@dataclass(frozen=True, slots=True)
class CategoryCount:
    """DTO de uma categoria e sua quantidade de registros."""

    label: str
    count: int


class DashboardService:
    """Calcula contagens, percentuais e distribuições do dashboard."""

    def __init__(self, repository: PerformanceRepository) -> None:
        self.repository = repository

    def total_registros(self) -> int:
        return self._safe(self.repository.contar)

    def total_atrasadas(self) -> int:
        return len(self._safe(self.repository.buscar_atrasadas))

    def total_em_aberto(self) -> int:
        return len(self._safe(self.repository.buscar_em_aberto))

    def total_entregues(self) -> int:
        return self._safe(
            self.repository.contar,
            PerformanceFilters(situacao="ENTREGUE"),
        )

    def total_devolvidas(self) -> int:
        return len(self._safe(self.repository.buscar_devolvidas))

    def percentual_atraso(self) -> float:
        return self._percentage(self.total_atrasadas(), self.total_registros())

    def percentual_entregues(self) -> float:
        return self._percentage(self.total_entregues(), self.total_registros())

    def percentual_devolvidas(self) -> float:
        return self._percentage(self.total_devolvidas(), self.total_registros())

    def transportadoras(self) -> tuple[CategoryCount, ...]:
        return self._distribution("Transportadora")

    def ufs(self) -> tuple[CategoryCount, ...]:
        return self._distribution("UF Destino")

    def cidades(self) -> tuple[CategoryCount, ...]:
        return self._distribution("Cidade Destino")

    @staticmethod
    def _percentage(part: int, total: int) -> float:
        return round((part / total) * 100, 2) if total else 0.0

    def _distribution(self, column_name: str) -> tuple[CategoryCount, ...]:
        records = self._safe(self.repository.listar)
        counter: Counter[str] = Counter()
        for record in records:
            value = record[column_name]
            if value is not None and str(value).strip():
                counter[str(value).strip()] += 1
        return tuple(
            CategoryCount(label, count)
            for label, count in sorted(
                counter.items(), key=lambda item: (-item[1], item[0])
            )
        )

    def _safe(
        self,
        operation: Callable[..., _Result],
        *args: object,
    ) -> _Result:
        try:
            return operation(*args)
        except RepositoryError as error:
            raise DashboardError(
                "Não foi possível calcular os indicadores do dashboard."
            ) from error
