"""Consultas de leitura de Performance Entrega."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from active_sync.persistence import DatabaseManager, PERFORMANCE_TABLE
from active_sync.transformer.schema import TRANSFORMER_SCHEMA

from .exceptions import InvalidQueryError, RepositoryError
from .models import PerformanceEntrega, PerformanceFilters


_COLUMN_NAMES = tuple(column.name for column in TRANSFORMER_SCHEMA)
_COLUMN_SET = frozenset(_COLUMN_NAMES)
_SELECT_COLUMNS = ", ".join(f'"{name}"' for name in _COLUMN_NAMES)
_BASE_SELECT = f'SELECT {_SELECT_COLUMNS} FROM "{PERFORMANCE_TABLE}"'


def _iso_date(value: date | str, field_name: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as error:
        raise InvalidQueryError(
            f"{field_name} deve utilizar o formato ISO YYYY-MM-DD."
        ) from error


def _validate_pagination(limit: int | None, offset: int) -> None:
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
    ):
        raise InvalidQueryError("limit deve ser um inteiro maior que zero.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise InvalidQueryError("offset deve ser um inteiro maior ou igual a zero.")


class PerformanceRepository:
    """Única interface de leitura da tabela performance_entrega."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def listar(
        self,
        filters: PerformanceFilters | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
        order_by: str = "Nota Fiscal",
        descending: bool = False,
    ) -> list[PerformanceEntrega]:
        """Lista registros com filtros, ordenação e paginação opcionais."""
        _validate_pagination(limit, offset)
        if order_by not in _COLUMN_SET:
            raise InvalidQueryError(f"Coluna de ordenação inválida: {order_by!r}.")
        clauses, parameters = self._filter_clauses(filters or PerformanceFilters())
        return self._select(
            clauses,
            parameters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )

    def buscar_por_nf(self, nota_fiscal: str) -> list[PerformanceEntrega]:
        """Busca todas as ocorrências de uma Nota Fiscal."""
        return self._select(['"Nota Fiscal" = ?'], [nota_fiscal])

    def buscar_por_transportadora(
        self,
        transportadora: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PerformanceEntrega]:
        """Busca registros de uma transportadora com paginação opcional."""
        return self.listar(
            PerformanceFilters(transportadora=transportadora),
            limit=limit,
            offset=offset,
        )

    def buscar_por_periodo(
        self,
        periodo_inicio: date | str,
        periodo_fim: date | str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PerformanceEntrega]:
        """Busca pelo intervalo inclusivo da data de Saída."""
        return self.listar(
            PerformanceFilters(
                periodo_inicio=periodo_inicio,
                periodo_fim=periodo_fim,
            ),
            limit=limit,
            offset=offset,
            order_by="Saída",
        )

    def buscar_atrasadas(self) -> list[PerformanceEntrega]:
        """Busca registros cuja Situação é ATRASADA."""
        return self.listar(PerformanceFilters(situacao="ATRASADA"))

    def buscar_em_aberto(self) -> list[PerformanceEntrega]:
        """Busca registros cuja Situação é EM ABERTO."""
        return self.listar(PerformanceFilters(situacao="EM ABERTO"))

    def buscar_devolvidas(self) -> list[PerformanceEntrega]:
        """Busca devoluções pela Flag homologada ou pela Situação."""
        return self._select(
            ['("Flag Devolução NF" = ? OR "Situação" = ?)'],
            [1, "DEVOLVIDA"],
        )

    def contar(self, filters: PerformanceFilters | None = None) -> int:
        """Conta registros, aceitando os mesmos filtros combináveis."""
        clauses, parameters = self._filter_clauses(filters or PerformanceFilters())
        sql = f'SELECT COUNT(*) FROM "{PERFORMANCE_TABLE}"'
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        try:
            return int(self.database.execute(sql, parameters).fetchone()[0])
        except Exception as error:
            raise RepositoryError("Falha ao contar registros.") from error

    def existe_nf(self, nota_fiscal: str) -> bool:
        """Informa se existe ao menos uma ocorrência da Nota Fiscal."""
        sql = (
            f'SELECT EXISTS(SELECT 1 FROM "{PERFORMANCE_TABLE}" '
            'WHERE "Nota Fiscal" = ?)'
        )
        try:
            return bool(self.database.execute(sql, (nota_fiscal,)).fetchone()[0])
        except Exception as error:
            raise RepositoryError("Falha ao verificar a Nota Fiscal.") from error

    def _filter_clauses(
        self,
        filters: PerformanceFilters,
    ) -> tuple[list[str], list[Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        equality_filters = (
            ("Transportadora", filters.transportadora),
            ("UF Destino", filters.uf_destino),
            ("Cidade Destino", filters.cidade_destino),
            ("Prazo", filters.prazo),
            ("Situação", filters.situacao),
        )
        for column_name, value in equality_filters:
            if value is not None:
                clauses.append(f'"{column_name}" = ?')
                parameters.append(value)
        if filters.periodo_inicio is not None:
            clauses.append('"Saída" >= ?')
            parameters.append(_iso_date(filters.periodo_inicio, "periodo_inicio"))
        if filters.periodo_fim is not None:
            clauses.append('"Saída" <= ?')
            parameters.append(_iso_date(filters.periodo_fim, "periodo_fim"))
        if (
            filters.periodo_inicio is not None
            and filters.periodo_fim is not None
            and parameters[-2] > parameters[-1]
        ):
            raise InvalidQueryError(
                "periodo_inicio não pode ser posterior a periodo_fim."
            )
        return clauses, parameters

    def _select(
        self,
        clauses: Sequence[str],
        parameters: Sequence[Any],
        *,
        limit: int | None = None,
        offset: int = 0,
        order_by: str = "Nota Fiscal",
        descending: bool = False,
    ) -> list[PerformanceEntrega]:
        _validate_pagination(limit, offset)
        if order_by not in _COLUMN_SET:
            raise InvalidQueryError(f"Coluna de ordenação inválida: {order_by!r}.")
        sql = _BASE_SELECT
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        direction = "DESC" if descending else "ASC"
        sql += f' ORDER BY "{order_by}" {direction}'
        query_parameters = list(parameters)
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            query_parameters.extend((limit, offset))
        elif offset:
            sql += " LIMIT ? OFFSET ?"
            query_parameters.extend((-1, offset))
        try:
            rows = self.database.execute(sql, query_parameters).fetchall()
        except Exception as error:
            raise RepositoryError("Falha ao consultar performance_entrega.") from error
        return [PerformanceEntrega.from_mapping(row) for row in rows]
