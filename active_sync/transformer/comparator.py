"""Comparação funcional entre resultados Python e Power Query."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, Sequence

import pandas as pd

from .columns import DATE_COLUMNS, NUMERIC_COLUMNS, TEXT_COLUMNS
from .snapshot_validator import (
    DEFAULT_ALIGNMENT_KEYS,
    SnapshotStatus,
    SnapshotValidationResult,
    TEMPORAL_COLUMNS,
    validate_snapshot_compatibility,
)
from .normalization import normalize_null, safe_number_series


_MISSING_ROW: Final[object] = object()
_MISSING_COLUMN: Final[object] = object()
_MISSING_LABEL: Final[str] = "<AUSENTE>"


@dataclass(frozen=True, slots=True)
class CellDivergence:
    """Diferença encontrada em uma célula, usando linha de dados iniciada em 1."""

    row_number: int
    column: str
    python_value: Any
    powerquery_value: Any


@dataclass(frozen=True, slots=True)
class ColumnComparison:
    """Métricas de equivalência de uma coluna."""

    column: str
    equal_records: int
    different_records: int
    equivalence_percent: float
    python_populated_records: int
    powerquery_populated_records: int
    comparable_equal_records: int
    comparable_different_records: int
    comparable_equivalence_percent: float

    @property
    def total_records(self) -> int:
        return self.equal_records + self.different_records

    @property
    def comparable_total_records(self) -> int:
        return self.comparable_equal_records + self.comparable_different_records


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """Relatório imutável da comparação entre os dois DataFrames."""

    python_row_count: int
    powerquery_row_count: int
    python_column_count: int
    powerquery_column_count: int
    column_order_matches: bool
    alignment_keys: tuple[str, ...]
    matched_row_count: int
    structural_errors: tuple[str, ...]
    column_results: tuple[ColumnComparison, ...]
    divergences: tuple[CellDivergence, ...]
    overall_equivalence_percent: float
    temporally_comparable_row_count: int
    temporally_excluded_row_count: int
    comparable_overall_equivalence_percent: float
    snapshot_validation: SnapshotValidationResult | None = None

    @property
    def is_structurally_equivalent(self) -> bool:
        return not self.structural_errors

    @property
    def is_fully_equivalent(self) -> bool:
        return self.is_structurally_equivalent and math.isclose(
            self.overall_equivalence_percent,
            100.0,
        )

    def result_for(self, column: str) -> ColumnComparison:
        """Retorna as métricas de uma coluna ou levanta KeyError."""
        return next(result for result in self.column_results if result.column == column)

    def to_text(self, max_divergences: int | None = None) -> str:
        """Renderiza um relatório legível; por padrão inclui todas as diferenças."""
        lines: list[str] = []
        if self.snapshot_validation is not None:
            lines.extend(self.snapshot_validation.to_text().rstrip().splitlines())
            lines.append("")
        lines.extend([
            "RELATÓRIO DE EQUIVALÊNCIA — PYTHON X POWER QUERY",
            "",
            "Estrutura",
            f"Linhas Python: {self.python_row_count}",
            f"Linhas Power Query: {self.powerquery_row_count}",
            f"Colunas Python: {self.python_column_count}",
            f"Colunas Power Query: {self.powerquery_column_count}",
            f"Ordem das colunas: {'OK' if self.column_order_matches else 'DIVERGENTE'}",
        ])
        if self.alignment_keys:
            lines.extend(
                [
                    f"Alinhamento por: {list(self.alignment_keys)}",
                    f"Linhas associadas pela chave: {self.matched_row_count}",
                ]
            )
        if self.structural_errors:
            lines.extend(["", "Divergências estruturais"])
            lines.extend(f"- {error}" for error in self.structural_errors)

        lines.extend(["", "Equivalência por coluna"])
        for result in self.column_results:
            lines.append(
                f"{result.column}: {result.equivalence_percent:.2f}% "
                f"({result.equal_records} iguais; "
                f"{result.different_records} diferentes; "
                f"preenchidos Python={result.python_populated_records}; "
                f"Power Query={result.powerquery_populated_records}; "
                "comparáveis temporalmente="
                f"{result.comparable_equivalence_percent:.2f}% "
                f"({result.comparable_equal_records} iguais; "
                f"{result.comparable_different_records} diferentes))"
            )

        lines.extend(
            [
                "",
                "Equivalência geral dos valores",
                f"{self.overall_equivalence_percent:.2f}%",
                "",
                "Equivalência nos registros temporalmente comparáveis",
                f"Linhas comparáveis: {self.temporally_comparable_row_count}",
                f"Linhas excluídas por snapshot: {self.temporally_excluded_row_count}",
                f"Equivalência comparável: {self.comparable_overall_equivalence_percent:.2f}%",
                "",
                "Divergências célula a célula",
            ]
        )
        selected = self.divergences
        if max_divergences is not None:
            selected = selected[:max_divergences]
        if not selected:
            lines.append("Nenhuma divergência encontrada.")
        for divergence in selected:
            lines.extend(
                [
                    "",
                    f"Linha {divergence.row_number}",
                    f"Coluna: {divergence.column}",
                    f"Python: {_display_value(divergence.python_value)}",
                    f"Power Query: {_display_value(divergence.powerquery_value)}",
                ]
            )
        omitted = len(self.divergences) - len(selected)
        if omitted:
            lines.extend(["", f"{omitted} divergências adicionais omitidas nesta visualização."])
        return "\n".join(lines) + "\n"


def _display_value(value: Any) -> str:
    if value is _MISSING_ROW or value is _MISSING_COLUMN:
        return _MISSING_LABEL
    normalized = normalize_null(value)
    return "None" if normalized is None else repr(value)


def _normalized_text(value: Any) -> str | None:
    normalized = normalize_null(value)
    if normalized is None:
        return None
    if isinstance(normalized, int) and not isinstance(normalized, bool):
        text = str(normalized)
    elif isinstance(normalized, float) and normalized.is_integer():
        text = str(int(normalized))
    else:
        text = str(normalized)
    return re.sub(r"\s+", " ", text.strip()).casefold() or None


def _normalized_number(value: Any) -> Decimal | tuple[str, str | None] | None:
    normalized = normalize_null(value)
    if normalized is None:
        return None
    number = safe_number_series(pd.Series([normalized], dtype="object")).iloc[0]
    if pd.isna(number):
        return ("invalid-number", _normalized_text(normalized))
    try:
        return Decimal(str(number)).normalize()
    except InvalidOperation:
        return None


def _normalized_date(value: Any) -> date | tuple[str, str | None] | None:
    normalized = normalize_null(value)
    if normalized is None:
        return None
    if isinstance(normalized, (int, float)) and not isinstance(normalized, bool):
        parsed = pd.to_datetime(
            normalized,
            unit="D",
            origin="1899-12-30",
            errors="coerce",
        )
    else:
        parsed = pd.to_datetime(
            normalized,
            errors="coerce",
            format="mixed",
            dayfirst=True,
        )
    if pd.isna(parsed):
        return ("invalid-date", _normalized_text(normalized))
    if isinstance(parsed, pd.Timestamp):
        return parsed.date()
    if isinstance(parsed, datetime):
        return parsed.date()
    return parsed


def _normalize_for_column(value: Any, column: str) -> Any:
    if value is _MISSING_ROW or value is _MISSING_COLUMN:
        return value
    if column in DATE_COLUMNS:
        return _normalized_date(value)
    if column in NUMERIC_COLUMNS:
        return _normalized_number(value)
    return _normalized_text(value)


def _normalization_kind(
    column: str,
    powerquery_series: pd.Series | None,
) -> str:
    if powerquery_series is None:
        if column in DATE_COLUMNS:
            return "date"
        if column in NUMERIC_COLUMNS:
            return "number"
        return "text"
    populated = [normalize_null(value) for value in powerquery_series]
    populated = [value for value in populated if value is not None]
    if not populated:
        if column in DATE_COLUMNS:
            return "date"
        if column in NUMERIC_COLUMNS:
            return "number"
        return "text"
    if column in DATE_COLUMNS:
        if any(isinstance(value, (date, datetime, pd.Timestamp)) for value in populated):
            return "date"
        parsed = pd.to_datetime(
            pd.Series(populated, dtype="object"),
            errors="coerce",
            format="mixed",
            dayfirst=True,
        )
        return "date" if parsed.notna().mean() >= 0.8 else "text"
    if column in NUMERIC_COLUMNS:
        parsed = safe_number_series(pd.Series(populated, dtype="object"))
        return "number" if parsed.notna().mean() >= 0.8 else "text"
    if column in TEXT_COLUMNS:
        return "text"
    if all(
        isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
        for value in populated
    ):
        return "number"
    return "text"


def _normalize_with_kind(value: Any, kind: str) -> Any:
    if value is _MISSING_ROW or value is _MISSING_COLUMN:
        return value
    if kind == "date":
        return _normalized_date(value)
    if kind == "number":
        return _normalized_number(value)
    return _normalized_text(value)


def _unique_columns(columns: pd.Index) -> list[str]:
    return list(dict.fromkeys(str(column) for column in columns))


def _duplicate_columns(frame: pd.DataFrame) -> list[str]:
    return _unique_columns(frame.columns[frame.columns.duplicated(keep=False)])


def _comparison_columns(
    python_columns: list[str],
    powerquery_columns: list[str],
) -> list[str]:
    return list(dict.fromkeys([*powerquery_columns, *python_columns]))


def _positional_pairs(
    python_row_count: int,
    powerquery_row_count: int,
) -> list[tuple[int | None, int | None]]:
    return [
        (
            position if position < python_row_count else None,
            position if position < powerquery_row_count else None,
        )
        for position in range(max(python_row_count, powerquery_row_count))
    ]


def _key_for_row(
    frame: pd.DataFrame,
    position: int,
    key_columns: tuple[str, ...],
    normalization_kinds: dict[str, str],
    side: str,
) -> tuple[Any, ...]:
    key = tuple(
        _normalize_with_kind(
            frame[column].iloc[position],
            normalization_kinds[column],
        )
        for column in key_columns
    )
    if any(value is None for value in key):
        return (side, position, *key)
    return key


def _aligned_pairs(
    df_python: pd.DataFrame,
    df_powerquery: pd.DataFrame,
    key_columns: tuple[str, ...],
    normalization_kinds: dict[str, str],
) -> tuple[list[tuple[int | None, int | None]], int, int]:
    python_slots: dict[tuple[Any, ...], list[int]] = {}
    for position in range(len(df_python)):
        key = _key_for_row(
            df_python,
            position,
            key_columns,
            normalization_kinds,
            "python",
        )
        python_slots.setdefault(key, []).append(position)

    duplicate_keys = sum(len(positions) - 1 for positions in python_slots.values())
    pairs: list[tuple[int | None, int | None]] = []
    matched_rows = 0
    used_python: set[int] = set()
    for powerquery_position in range(len(df_powerquery)):
        key = _key_for_row(
            df_powerquery,
            powerquery_position,
            key_columns,
            normalization_kinds,
            "powerquery",
        )
        candidates = python_slots.get(key, [])
        python_position = candidates.pop(0) if candidates else None
        if python_position is not None:
            used_python.add(python_position)
            matched_rows += 1
        pairs.append((python_position, powerquery_position))

    pairs.extend(
        (position, None)
        for position in range(len(df_python))
        if position not in used_python
    )
    return pairs, matched_rows, duplicate_keys


def _temporally_comparable_mask(
    df_python: pd.DataFrame,
    df_powerquery: pd.DataFrame,
    pairs: list[tuple[int | None, int | None]],
) -> tuple[bool, ...]:
    common_columns = [
        column
        for column in TEMPORAL_COLUMNS
        if column in df_python.columns and column in df_powerquery.columns
    ]
    if not common_columns:
        return tuple(True for _ in pairs)

    mask: list[bool] = []
    for python_position, powerquery_position in pairs:
        comparable = python_position is not None and powerquery_position is not None
        if comparable:
            for column in common_columns:
                python_date = _normalized_date(
                    df_python[column].iloc[python_position]
                )
                powerquery_date = _normalized_date(
                    df_powerquery[column].iloc[powerquery_position]
                )
                if isinstance(python_date, tuple) or isinstance(powerquery_date, tuple):
                    comparable = False
                    break
                if (python_date is None) != (powerquery_date is None):
                    comparable = False
                    break
        mask.append(comparable)
    return tuple(mask)


def _structural_errors(
    df_python: pd.DataFrame,
    df_powerquery: pd.DataFrame,
    python_columns: list[str],
    powerquery_columns: list[str],
) -> list[str]:
    errors: list[str] = []
    if len(df_python) != len(df_powerquery):
        errors.append(
            "Quantidade de linhas divergente: "
            f"Python={len(df_python)}; Power Query={len(df_powerquery)}."
        )
    if len(python_columns) != len(powerquery_columns):
        errors.append(
            "Quantidade de colunas divergente: "
            f"Python={len(python_columns)}; Power Query={len(powerquery_columns)}."
        )
    if python_columns != powerquery_columns:
        errors.append("Os nomes ou a ordem das colunas são divergentes.")
    only_powerquery = [column for column in powerquery_columns if column not in python_columns]
    only_python = [column for column in python_columns if column not in powerquery_columns]
    if only_powerquery:
        errors.append(f"Colunas ausentes no Python: {only_powerquery}.")
    if only_python:
        errors.append(f"Colunas ausentes no Power Query: {only_python}.")
    python_duplicates = _duplicate_columns(df_python)
    powerquery_duplicates = _duplicate_columns(df_powerquery)
    if python_duplicates:
        errors.append(f"Colunas duplicadas no Python: {python_duplicates}.")
    if powerquery_duplicates:
        errors.append(f"Colunas duplicadas no Power Query: {powerquery_duplicates}.")
    return errors


def compare_dataframes(
    df_python: pd.DataFrame,
    df_powerquery: pd.DataFrame,
    logger: logging.Logger | None = None,
    key_columns: Sequence[str] | None = None,
    *,
    require_compatible_snapshot: bool = False,
    validate_snapshot: bool = True,
    raw_source: str | Path | None = None,
    reference_source: str | Path | None = None,
) -> ComparisonReport:
    """Compara valores por posição ou após alinhamento explícito por chave."""
    snapshot_validation = None
    if validate_snapshot:
        snapshot_validation = validate_snapshot_compatibility(
            df_python,
            df_powerquery,
            key_columns=tuple(key_columns or DEFAULT_ALIGNMENT_KEYS),
            raw_source=raw_source,
            reference_source=reference_source,
            require_compatible=require_compatible_snapshot,
        )
        if logger:
            if snapshot_validation.status in {
                SnapshotStatus.TEMPORAL_MISMATCH,
                SnapshotStatus.INCONCLUSIVE,
            }:
                logger.warning(
                    "Snapshot validation: %s — %s",
                    snapshot_validation.status.value,
                    snapshot_validation.conclusion,
                )
            else:
                logger.info(
                    "Snapshot validation: %s",
                    snapshot_validation.status.value,
                )
    python_columns = [str(column) for column in df_python.columns]
    powerquery_columns = [str(column) for column in df_powerquery.columns]
    structural_errors = _structural_errors(
        df_python,
        df_powerquery,
        python_columns,
        powerquery_columns,
    )
    comparison_columns = _comparison_columns(python_columns, powerquery_columns)
    normalization_kinds = {
        column: _normalization_kind(
            column,
            df_powerquery[column]
            if powerquery_columns.count(column) == 1
            else None,
        )
        for column in comparison_columns
    }
    alignment_keys = tuple(key_columns or ())
    invalid_keys = [
        column
        for column in alignment_keys
        if python_columns.count(column) != 1 or powerquery_columns.count(column) != 1
    ]
    if invalid_keys:
        structural_errors.append(
            "Não foi possível alinhar pelas chaves ausentes ou duplicadas: "
            f"{invalid_keys}."
        )
        pairs = _positional_pairs(len(df_python), len(df_powerquery))
        matched_row_count = min(len(df_python), len(df_powerquery))
        alignment_keys = ()
    elif alignment_keys:
        pairs, matched_row_count, duplicate_key_count = _aligned_pairs(
            df_python,
            df_powerquery,
            alignment_keys,
            normalization_kinds,
        )
        if duplicate_key_count:
            structural_errors.append(
                "A chave de alinhamento possui "
                f"{duplicate_key_count} ocorrência(s) adicional(is) no Python; "
                "duplicidades foram associadas pela ordem de aparição."
            )
    else:
        pairs = _positional_pairs(len(df_python), len(df_powerquery))
        matched_row_count = min(len(df_python), len(df_powerquery))
    row_count = len(pairs)
    comparable_mask = _temporally_comparable_mask(
        df_python,
        df_powerquery,
        pairs,
    )
    comparable_row_count = sum(comparable_mask)
    python_counts = pd.Series(python_columns).value_counts().to_dict()
    powerquery_counts = pd.Series(powerquery_columns).value_counts().to_dict()
    divergences: list[CellDivergence] = []
    results: list[ColumnComparison] = []
    total_equal = 0
    total_compared = 0
    comparable_total_equal = 0
    comparable_total_compared = 0

    for column in comparison_columns:
        python_available = python_counts.get(column, 0) == 1
        powerquery_available = powerquery_counts.get(column, 0) == 1
        equal_records = 0
        different_records = 0
        python_populated_records = 0
        powerquery_populated_records = 0
        comparable_equal_records = 0
        comparable_different_records = 0

        for position, (python_position, powerquery_position) in enumerate(pairs):
            if not python_available:
                python_value = _MISSING_COLUMN
            elif python_position is None:
                python_value = _MISSING_ROW
            else:
                python_value = df_python[column].iloc[python_position]

            if not powerquery_available:
                powerquery_value = _MISSING_COLUMN
            elif powerquery_position is None:
                powerquery_value = _MISSING_ROW
            else:
                powerquery_value = df_powerquery[column].iloc[powerquery_position]

            kind = normalization_kinds[column]
            python_normalized = _normalize_with_kind(python_value, kind)
            powerquery_normalized = _normalize_with_kind(powerquery_value, kind)
            if python_normalized not in (None, _MISSING_ROW, _MISSING_COLUMN):
                python_populated_records += 1
            if powerquery_normalized not in (None, _MISSING_ROW, _MISSING_COLUMN):
                powerquery_populated_records += 1
            if python_normalized == powerquery_normalized:
                equal_records += 1
                if comparable_mask[position]:
                    comparable_equal_records += 1
            else:
                different_records += 1
                if comparable_mask[position]:
                    comparable_different_records += 1
                divergences.append(
                    CellDivergence(
                        row_number=position + 1,
                        column=column,
                        python_value=python_value,
                        powerquery_value=powerquery_value,
                    )
                )

        if row_count:
            percent = round(equal_records * 100 / row_count, 2)
        else:
            percent = 100.0 if python_available and powerquery_available else 0.0
        if comparable_row_count:
            comparable_percent = round(
                comparable_equal_records * 100 / comparable_row_count,
                2,
            )
        else:
            comparable_percent = 0.0
        results.append(
            ColumnComparison(
                column=column,
                equal_records=equal_records,
                different_records=different_records,
                equivalence_percent=percent,
                python_populated_records=python_populated_records,
                powerquery_populated_records=powerquery_populated_records,
                comparable_equal_records=comparable_equal_records,
                comparable_different_records=comparable_different_records,
                comparable_equivalence_percent=comparable_percent,
            )
        )
        total_equal += equal_records
        total_compared += row_count
        comparable_total_equal += comparable_equal_records
        comparable_total_compared += comparable_row_count

    if total_compared:
        overall_percent = round(total_equal * 100 / total_compared, 2)
    else:
        overall_percent = 100.0 if not structural_errors else 0.0
    if comparable_total_compared:
        comparable_overall_percent = round(
            comparable_total_equal * 100 / comparable_total_compared,
            2,
        )
    else:
        comparable_overall_percent = 0.0
    report = ComparisonReport(
        python_row_count=len(df_python),
        powerquery_row_count=len(df_powerquery),
        python_column_count=len(python_columns),
        powerquery_column_count=len(powerquery_columns),
        column_order_matches=python_columns == powerquery_columns,
        alignment_keys=alignment_keys,
        matched_row_count=matched_row_count,
        structural_errors=tuple(structural_errors),
        column_results=tuple(results),
        divergences=tuple(divergences),
        overall_equivalence_percent=overall_percent,
        temporally_comparable_row_count=comparable_row_count,
        temporally_excluded_row_count=row_count - comparable_row_count,
        comparable_overall_equivalence_percent=comparable_overall_percent,
        snapshot_validation=snapshot_validation,
    )
    if logger:
        logger.info(
            "Comparação concluída: equivalência geral %.2f%%; %d divergências",
            report.overall_equivalence_percent,
            len(report.divergences),
        )
    return report


def write_comparison_report(
    report: ComparisonReport,
    output_path: str | Path = Path("equivalencia_powerquery.txt"),
) -> Path:
    """Grava o relatório textual completo em UTF-8 de forma atômica."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(report.to_text(), encoding="utf-8")
    temporary.replace(destination)
    return destination
