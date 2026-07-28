"""Validação dos contratos de entrada e saída do transformer."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from pandas.api.types import (
    is_datetime64_any_dtype,
    is_bool_dtype,
    is_numeric_dtype,
    is_object_dtype,
    is_string_dtype,
)

from .columns import BOOLEAN_COLUMNS, DATE_COLUMNS, NUMERIC_COLUMNS, OUTPUT_COLUMNS, TEXT_COLUMNS
from .mapping import COLUMN_MAPPING, RETURN_SOURCE_COLUMNS


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Resultado explícito de uma validação estrutural."""

    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _duplicated_columns(frame: pd.DataFrame) -> list[str]:
    return [str(column) for column in frame.columns[frame.columns.duplicated()].tolist()]


def validate_source_dataframe(frame: pd.DataFrame) -> ValidationResult:
    """Verifica duplicidades e colunas de origem necessárias ao mapeamento atual."""
    errors: list[str] = []
    duplicates = _duplicated_columns(frame)
    if duplicates:
        errors.append(f"A entrada contém colunas duplicadas: {duplicates}")
    required = {source for source in COLUMN_MAPPING.values() if source is not None}
    required.update(RETURN_SOURCE_COLUMNS)
    missing = sorted(required - set(str(column) for column in frame.columns))
    if missing:
        errors.append(f"A entrada não contém colunas obrigatórias: {missing}")
    return ValidationResult(tuple(errors))


def validate_output_dataframe(frame: pd.DataFrame) -> ValidationResult:
    """Verifica nomes, ordem, duplicidades e tipos compatíveis da saída."""
    errors: list[str] = []
    actual = tuple(str(column) for column in frame.columns)
    duplicates = _duplicated_columns(frame)
    if duplicates:
        errors.append(f"A saída contém colunas duplicadas: {duplicates}")
    if actual != OUTPUT_COLUMNS:
        errors.append(
            "A ordem ou os nomes das colunas estão incorretos. "
            f"Esperado: {list(OUTPUT_COLUMNS)}; recebido: {list(actual)}"
        )
        return ValidationResult(tuple(errors))

    for column in OUTPUT_COLUMNS:
        series = frame[column]
        if series.isna().all():
            continue
        if column in DATE_COLUMNS and not is_datetime64_any_dtype(series.dtype):
            errors.append(f"A coluna {column!r} deve ser compatível com data.")
        elif column in NUMERIC_COLUMNS and not is_numeric_dtype(series.dtype):
            errors.append(f"A coluna {column!r} deve ser compatível com número.")
        elif column in BOOLEAN_COLUMNS and not is_bool_dtype(series.dtype):
            errors.append(f"A coluna {column!r} deve ser compatível com booleano.")
        elif column in TEXT_COLUMNS and not (
            is_object_dtype(series.dtype) or is_string_dtype(series.dtype)
        ):
            errors.append(f"A coluna {column!r} deve ser compatível com texto.")
    return ValidationResult(tuple(errors))
