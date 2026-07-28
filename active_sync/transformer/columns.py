"""Visões derivadas do contrato persistente da saída Performance Entrega."""

from typing import Final

from .schema import TRANSFORMER_SCHEMA


OUTPUT_COLUMNS: Final[tuple[str, ...]] = tuple(
    column.name for column in TRANSFORMER_SCHEMA
)

DATE_COLUMNS: Final[frozenset[str]] = frozenset(
    column.name
    for column in TRANSFORMER_SCHEMA
    if column.pandas_dtype == "datetime64[ns]"
)
NUMERIC_COLUMNS: Final[frozenset[str]] = frozenset(
    column.name
    for column in TRANSFORMER_SCHEMA
    if column.pandas_dtype in {"Float64", "Int64"}
)
BOOLEAN_COLUMNS: Final[frozenset[str]] = frozenset(
    column.name for column in TRANSFORMER_SCHEMA if column.pandas_dtype == "bool"
)
TEXT_COLUMNS: Final[frozenset[str]] = (
    frozenset(OUTPUT_COLUMNS) - DATE_COLUMNS - NUMERIC_COLUMNS - BOOLEAN_COLUMNS
)
