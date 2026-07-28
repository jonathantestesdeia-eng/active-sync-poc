"""Validação não destrutiva da compatibilidade temporal entre snapshots."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Sequence

import pandas as pd

from active_sync.exceptions import IncompatibleSnapshotError

from .normalization import normalize_null


TEMPORAL_COLUMNS: Final[tuple[str, ...]] = ("Saída", "Previsão", "Entrega")
DEFAULT_ALIGNMENT_KEYS: Final[tuple[str, ...]] = ("Nota Fiscal",)

# Evidência auxiliar: 90% evita classificar poucos outliers como tendência temporal.
NEARLY_ALL_LATER_RATIO: Final[float] = 0.90


class SnapshotStatus(StrEnum):
    """Classificações possíveis para a relação temporal entre dois arquivos."""

    COMPATIBLE = "COMPATIBLE"
    TEMPORAL_MISMATCH = "TEMPORAL_MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"
    DATA_DIVERGENCE = "DATA_DIVERGENCE"


@dataclass(frozen=True, slots=True)
class TemporalColumnEvidence:
    """Métricas auditáveis de uma coluna temporal alinhada por chave."""

    column: str
    raw_filled_count: int
    reference_filled_count: int
    raw_invalid_count: int
    reference_invalid_count: int
    raw_min_date: date | None
    raw_max_date: date | None
    reference_min_date: date | None
    reference_max_date: date | None
    same_date_count: int
    both_null_count: int
    only_raw_count: int
    only_reference_count: int
    conflicting_date_count: int
    raw_only_after_reference_max: int
    reference_only_after_raw_max: int

    @property
    def difference_count(self) -> int:
        return (
            self.only_raw_count
            + self.only_reference_count
            + self.conflicting_date_count
        )

    @property
    def raw_only_later_ratio(self) -> float:
        if not self.only_raw_count:
            return 0.0
        return self.raw_only_after_reference_max / self.only_raw_count

    @property
    def reference_only_later_ratio(self) -> float:
        if not self.only_reference_count:
            return 0.0
        return self.reference_only_after_raw_max / self.only_reference_count

    @property
    def raw_only_is_nearly_all_later(self) -> bool:
        return (
            self.only_raw_count > 0
            and self.raw_only_later_ratio >= NEARLY_ALL_LATER_RATIO
        )

    @property
    def reference_only_is_nearly_all_later(self) -> bool:
        return (
            self.only_reference_count > 0
            and self.reference_only_later_ratio >= NEARLY_ALL_LATER_RATIO
        )


@dataclass(frozen=True, slots=True)
class SnapshotValidationResult:
    """Resultado completo da validação de compatibilidade temporal."""

    status: SnapshotStatus
    warnings: tuple[str, ...]
    columns: tuple[TemporalColumnEvidence, ...]
    alignment_keys: tuple[str, ...]
    matched_row_count: int
    raw_source: str | None
    reference_source: str | None
    executed_at: datetime
    conclusion: str

    @property
    def compatible(self) -> bool:
        return self.status is SnapshotStatus.COMPATIBLE

    @property
    def raw_max_dates(self) -> dict[str, date | None]:
        return {item.column: item.raw_max_date for item in self.columns}

    @property
    def reference_max_dates(self) -> dict[str, date | None]:
        return {item.column: item.reference_max_date for item in self.columns}

    @property
    def raw_filled_counts(self) -> dict[str, int]:
        return {item.column: item.raw_filled_count for item in self.columns}

    @property
    def reference_filled_counts(self) -> dict[str, int]:
        return {item.column: item.reference_filled_count for item in self.columns}

    def evidence_for(self, column: str) -> TemporalColumnEvidence:
        """Retorna as métricas de uma coluna temporal."""
        return next(item for item in self.columns if item.column == column)

    def to_text(self, include_heading: bool = True) -> str:
        """Renderiza o diagnóstico temporal em formato textual auditável."""
        lines: list[str] = []
        if include_heading:
            lines.extend(["SNAPSHOT VALIDATION", ""])
        lines.extend(
            [
                f"Status: {self.status.value}",
                f"Executado em: {self.executed_at.astimezone().isoformat(timespec='seconds')}",
                f"Arquivo bruto: {self.raw_source or '<não informado>'}",
                f"Arquivo de referência: {self.reference_source or '<não informado>'}",
                f"Alinhamento por: {list(self.alignment_keys)}",
                f"Linhas associadas: {self.matched_row_count}",
                "",
                "Colunas temporais avaliadas",
            ]
        )
        if not self.columns:
            lines.append("Nenhuma coluna temporal pôde ser avaliada.")
        for item in self.columns:
            lines.extend(
                [
                    "",
                    f"Coluna: {item.column}",
                    f"Preenchidos no bruto: {item.raw_filled_count}",
                    f"Preenchidos na referência: {item.reference_filled_count}",
                    f"Inválidos no bruto: {item.raw_invalid_count}",
                    f"Inválidos na referência: {item.reference_invalid_count}",
                    f"Menor data no bruto: {_format_date(item.raw_min_date)}",
                    f"Maior data no bruto: {_format_date(item.raw_max_date)}",
                    f"Menor data na referência: {_format_date(item.reference_min_date)}",
                    f"Maior data na referência: {_format_date(item.reference_max_date)}",
                    f"Mesma data preenchida: {item.same_date_count}",
                    f"Nulos nos dois lados: {item.both_null_count}",
                    f"Somente no bruto: {item.only_raw_count}",
                    f"Somente na referência: {item.only_reference_count}",
                    f"Datas conflitantes: {item.conflicting_date_count}",
                    "Exclusivos do bruto posteriores ao máximo da referência: "
                    f"{item.raw_only_after_reference_max}",
                    "Exclusivos da referência posteriores ao máximo do bruto: "
                    f"{item.reference_only_after_raw_max}",
                ]
            )
        if self.warnings:
            lines.extend(["", "Avisos"])
            lines.extend(f"- {warning}" for warning in self.warnings)
        lines.extend(["", "Conclusão", self.conclusion])
        return "\n".join(lines) + "\n"


def _format_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value is not None else "<nula>"


def _date_value(value: Any) -> tuple[date | None, bool]:
    normalized = normalize_null(value)
    if normalized is None:
        return None, False
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
        return None, True
    if isinstance(parsed, pd.Timestamp):
        return parsed.date(), False
    if isinstance(parsed, datetime):
        return parsed.date(), False
    return parsed, False


def _identifier(value: Any) -> str | None:
    normalized = normalize_null(value)
    if normalized is None:
        return None
    if isinstance(normalized, int) and not isinstance(normalized, bool):
        return str(normalized)
    if isinstance(normalized, float) and math.isfinite(normalized) and normalized.is_integer():
        return str(int(normalized))
    return str(normalized).strip().casefold()


def _row_key(frame: pd.DataFrame, position: int, keys: tuple[str, ...]) -> tuple[str | None, ...]:
    return tuple(_identifier(frame[column].iloc[position]) for column in keys)


def _align_positions(
    raw: pd.DataFrame,
    reference: pd.DataFrame,
    keys: tuple[str, ...],
) -> tuple[list[tuple[int | None, int | None]], int]:
    raw_slots: dict[tuple[str | None, ...], list[int]] = {}
    for position in range(len(raw)):
        key = _row_key(raw, position, keys)
        if any(value is None for value in key):
            continue
        raw_slots.setdefault(key, []).append(position)

    pairs: list[tuple[int | None, int | None]] = []
    used_raw: set[int] = set()
    matched = 0
    for position in range(len(reference)):
        key = _row_key(reference, position, keys)
        candidates = raw_slots.get(key, []) if all(value is not None for value in key) else []
        raw_position = candidates.pop(0) if candidates else None
        if raw_position is not None:
            used_raw.add(raw_position)
            matched += 1
        pairs.append((raw_position, position))
    pairs.extend(
        (position, None)
        for position in range(len(raw))
        if position not in used_raw
    )
    return pairs, matched


def _column_evidence(
    raw: pd.DataFrame,
    reference: pd.DataFrame,
    column: str,
    pairs: list[tuple[int | None, int | None]],
) -> TemporalColumnEvidence:
    raw_dates: list[date] = []
    reference_dates: list[date] = []
    raw_only_dates: list[date] = []
    reference_only_dates: list[date] = []
    raw_invalid = 0
    reference_invalid = 0
    same_date = 0
    both_null = 0
    conflicts = 0

    for raw_position, reference_position in pairs:
        raw_value = None if raw_position is None else raw[column].iloc[raw_position]
        reference_value = (
            None
            if reference_position is None
            else reference[column].iloc[reference_position]
        )
        raw_date, raw_is_invalid = _date_value(raw_value)
        reference_date, reference_is_invalid = _date_value(reference_value)
        raw_invalid += int(raw_is_invalid)
        reference_invalid += int(reference_is_invalid)
        if raw_date is not None:
            raw_dates.append(raw_date)
        if reference_date is not None:
            reference_dates.append(reference_date)
        if raw_date is None and reference_date is None:
            both_null += 1
        elif raw_date is not None and reference_date is None:
            raw_only_dates.append(raw_date)
        elif raw_date is None and reference_date is not None:
            reference_only_dates.append(reference_date)
        elif raw_date == reference_date:
            same_date += 1
        else:
            conflicts += 1

    raw_max = max(raw_dates, default=None)
    reference_max = max(reference_dates, default=None)
    raw_after = sum(
        reference_max is not None and value > reference_max
        for value in raw_only_dates
    )
    reference_after = sum(
        raw_max is not None and value > raw_max
        for value in reference_only_dates
    )
    return TemporalColumnEvidence(
        column=column,
        raw_filled_count=len(raw_dates),
        reference_filled_count=len(reference_dates),
        raw_invalid_count=raw_invalid,
        reference_invalid_count=reference_invalid,
        raw_min_date=min(raw_dates, default=None),
        raw_max_date=raw_max,
        reference_min_date=min(reference_dates, default=None),
        reference_max_date=reference_max,
        same_date_count=same_date,
        both_null_count=both_null,
        only_raw_count=len(raw_only_dates),
        only_reference_count=len(reference_only_dates),
        conflicting_date_count=conflicts,
        raw_only_after_reference_max=raw_after,
        reference_only_after_raw_max=reference_after,
    )


def _classify(columns: tuple[TemporalColumnEvidence, ...]) -> tuple[SnapshotStatus, str]:
    if not columns:
        return (
            SnapshotStatus.INCONCLUSIVE,
            "Não existem colunas temporais comuns suficientes para validar os snapshots.",
        )
    if any(item.conflicting_date_count for item in columns):
        return (
            SnapshotStatus.DATA_DIVERGENCE,
            "Existem datas diferentes em registros preenchidos nos dois arquivos; "
            "a divergência deve ser investigada como diferença de dados ou regra.",
        )
    if any(item.raw_invalid_count or item.reference_invalid_count for item in columns):
        return (
            SnapshotStatus.INCONCLUSIVE,
            "Foram encontrados valores temporais inválidos; a compatibilidade não "
            "pode ser afirmada com segurança.",
        )

    divergent = [item for item in columns if item.difference_count]
    if not divergent:
        return (
            SnapshotStatus.COMPATIBLE,
            "Não há evidência relevante de snapshots temporais diferentes.",
        )

    directions: set[str] = set()
    for item in divergent:
        if item.only_raw_count and item.only_reference_count:
            return (
                SnapshotStatus.INCONCLUSIVE,
                "Há preenchimentos exclusivos nos dois lados da mesma coluna, sem "
                "um padrão temporal unidirecional claro.",
            )
        if item.only_raw_count:
            directions.add("raw")
        if item.only_reference_count:
            directions.add("reference")
    if len(directions) == 1:
        side = "bruto" if "raw" in directions else "referência"
        return (
            SnapshotStatus.TEMPORAL_MISMATCH,
            f"Os preenchimentos adicionais aparecem somente no {side}, sem datas "
            "conflitantes quando ambos os arquivos possuem valor. Os arquivos "
            "provavelmente representam momentos diferentes da operação. A "
            "equivalência das colunas afetadas não pode ser validada de forma "
            "conclusiva com este par de arquivos.",
        )
    return (
        SnapshotStatus.INCONCLUSIVE,
        "As divergências temporais apontam para direções diferentes entre as "
        "colunas e não permitem determinar qual snapshot é mais recente.",
    )


def validate_snapshot_compatibility(
    raw: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    key_columns: Sequence[str] = DEFAULT_ALIGNMENT_KEYS,
    temporal_columns: Sequence[str] = TEMPORAL_COLUMNS,
    raw_source: str | Path | None = None,
    reference_source: str | Path | None = None,
    executed_at: datetime | None = None,
    require_compatible: bool = False,
) -> SnapshotValidationResult:
    """Analisa datas alinhadas por ocorrência sem modificar os DataFrames."""
    keys = tuple(key_columns)
    warnings: list[str] = []
    missing_keys = [
        column
        for column in keys
        if column not in raw.columns or column not in reference.columns
    ]
    if missing_keys:
        warnings.append(
            "Não foi possível alinhar porque as chaves estão ausentes em um dos "
            f"arquivos: {missing_keys}."
        )
        result = SnapshotValidationResult(
            status=SnapshotStatus.INCONCLUSIVE,
            warnings=tuple(warnings),
            columns=(),
            alignment_keys=keys,
            matched_row_count=0,
            raw_source=str(raw_source) if raw_source is not None else None,
            reference_source=(
                str(reference_source) if reference_source is not None else None
            ),
            executed_at=executed_at or datetime.now(timezone.utc),
            conclusion="As chaves necessárias para o alinhamento não estão disponíveis.",
        )
        _raise_if_required(result, require_compatible)
        return result

    pairs, matched = _align_positions(raw, reference, keys)
    common_columns: list[str] = []
    for column in temporal_columns:
        if column in raw.columns and column in reference.columns:
            common_columns.append(column)
        else:
            warnings.append(
                f"A coluna temporal {column!r} está ausente em um dos arquivos e "
                "não foi avaliada."
            )
    evidence = tuple(
        _column_evidence(raw, reference, column, pairs)
        for column in common_columns
    )
    status, conclusion = _classify(evidence)
    result = SnapshotValidationResult(
        status=status,
        warnings=tuple(warnings),
        columns=evidence,
        alignment_keys=keys,
        matched_row_count=matched,
        raw_source=str(raw_source) if raw_source is not None else None,
        reference_source=(str(reference_source) if reference_source is not None else None),
        executed_at=executed_at or datetime.now(timezone.utc),
        conclusion=conclusion,
    )
    _raise_if_required(result, require_compatible)
    return result


def _raise_if_required(
    result: SnapshotValidationResult,
    require_compatible: bool,
) -> None:
    if require_compatible and result.status in {
        SnapshotStatus.TEMPORAL_MISMATCH,
        SnapshotStatus.INCONCLUSIVE,
    }:
        raise IncompatibleSnapshotError(
            "Snapshot incompatível para comparação estrita: "
            f"{result.status.value}. {result.conclusion}"
        )


def write_snapshot_validation_report(
    result: SnapshotValidationResult,
    output_path: str | Path = Path("docs/snapshot_validation.txt"),
) -> Path:
    """Grava o diagnóstico temporal completo em UTF-8 de forma atômica."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(result.to_text(), encoding="utf-8")
    temporary.replace(destination)
    return destination
