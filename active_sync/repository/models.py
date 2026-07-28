"""Modelos de leitura derivados do contrato persistente oficial."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from types import MappingProxyType
from typing import Any, ClassVar, Mapping
import unicodedata

from active_sync.transformer.schema import TRANSFORMER_SCHEMA


def _python_alias(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")


PERSISTENT_COLUMNS: tuple[str, ...] = tuple(
    column.name for column in TRANSFORMER_SCHEMA
)
COLUMN_ALIASES: Mapping[str, str] = MappingProxyType(
    {_python_alias(name): name for name in PERSISTENT_COLUMNS}
)


@dataclass(frozen=True, slots=True)
class PerformanceEntrega:
    """Registro imutável com os 22 valores do contrato persistente."""

    _values: tuple[Any, ...]

    columns: ClassVar[tuple[str, ...]] = PERSISTENT_COLUMNS
    aliases: ClassVar[Mapping[str, str]] = COLUMN_ALIASES

    def __post_init__(self) -> None:
        if len(self._values) != len(self.columns):
            raise ValueError(
                f"PerformanceEntrega exige {len(self.columns)} valores; "
                f"recebeu {len(self._values)}."
            )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> PerformanceEntrega:
        """Cria o modelo seguindo a ordem oficial, sem duplicar campos."""
        available = set(values.keys())
        missing = [name for name in cls.columns if name not in available]
        if missing:
            raise ValueError(f"Registro sem colunas obrigatórias: {missing}.")
        return cls(tuple(values[name] for name in cls.columns))

    def __getitem__(self, column_name: str) -> Any:
        """Obtém um valor pelo nome persistente da coluna."""
        try:
            position = self.columns.index(column_name)
        except ValueError as error:
            raise KeyError(column_name) from error
        return self._values[position]

    def __getattr__(self, alias: str) -> Any:
        """Permite aliases Python derivados, como ``nota_fiscal``."""
        column_name = self.aliases.get(alias)
        if column_name is None:
            raise AttributeError(alias)
        return self[column_name]

    def as_dict(self) -> dict[str, Any]:
        """Converte o registro para o contrato persistente nominal."""
        return dict(zip(self.columns, self._values, strict=True))


@dataclass(frozen=True, slots=True)
class PerformanceFilters:
    """Filtros combináveis aceitos pela consulta de listagem."""

    transportadora: str | None = None
    uf_destino: str | None = None
    cidade_destino: str | None = None
    prazo: str | None = None
    situacao: str | None = None
    periodo_inicio: date | str | None = None
    periodo_fim: date | str | None = None


@dataclass(frozen=True, slots=True)
class SuperTrackMovement:
    """Movimento operacional preservado sem regras analíticas de Performance."""

    transportador_id: str
    serie_cte: str
    cte: str
    nota_fiscal: str
    chave_cte: str | None
    serie_nf: str | None
    pedido: str | None
    tipo_cte: str | None
    transportadora: str | None
    remetente: str | None
    destinatario: str | None
    cnpj_destinatario: str | None
    cidade_origem: str | None
    cidade_destino: str | None
    uf_destino: str | None
    emissao: str | None
    saida: str | None
    previsao: str | None
    entrega: str | None
    situacao: str
    observacao: str | None
    valor_frete: float | None
    data_atualizacao: str | None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> SuperTrackMovement:
        return cls(
            **{
                field_name: values[field_name]
                for field_name in cls.__dataclass_fields__
            }
        )

    @property
    def movement_id(self) -> str:
        return "|".join(
            (self.transportador_id, self.serie_cte, self.cte, self.nota_fiscal)
        )
