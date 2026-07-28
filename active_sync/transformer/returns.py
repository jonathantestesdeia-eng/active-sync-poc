"""Regras de devolução reproduzidas integralmente da consulta M oficial."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from active_sync.exceptions import TransformationValidationError

from .mapping import (
    RETURN_CTE_COLUMN,
    RETURN_DESTINATION_CITIES,
    RETURN_DESTINATION_COLUMN,
    RETURN_NOTE_COLUMN,
    RETURN_OBSERVATION_COLUMN,
    RETURN_ROUTE_COLUMN,
    RETURN_SOURCE_COLUMNS,
    RETURN_TEXT_TOKEN,
    RETURN_TYPE_COLUMN,
    RETURN_TYPE_LABEL,
)
from .normalization import identifier_as_text, normalize_null, trim_text


@dataclass(frozen=True, slots=True)
class _ReturnEvidence:
    """Resultados intermediários preservados na mesma ordem da consulta M."""

    flag_text: pd.Series
    destination_flag: pd.Series
    candidate_cte: pd.Series
    distinct_cte_count: pd.Series
    any_destination: pd.Series
    any_text: pd.Series
    grouped_ctes: pd.Series
    flag: pd.Series


def _validate_source(source: pd.DataFrame) -> None:
    missing = sorted(set(RETURN_SOURCE_COLUMNS) - set(str(column) for column in source.columns))
    if missing:
        raise TransformationValidationError(
            "A regra de devolução requer as colunas: " f"{missing}."
        )


def _text_from_m(value: Any) -> str | None:
    normalized = normalize_null(value)
    return None if normalized is None else str(normalized)


def _contains_return_text(source: pd.DataFrame) -> pd.Series:
    values: list[bool] = []
    for row in source.loc[
        :, [RETURN_TYPE_COLUMN, RETURN_OBSERVATION_COLUMN, RETURN_ROUTE_COLUMN]
    ].itertuples(index=False, name=None):
        combined = " ".join(
            text
            for text in (_text_from_m(value) for value in row)
            if text is not None
        ).upper()
        values.append(RETURN_TEXT_TOKEN in combined)
    return pd.Series(values, index=source.index, dtype="bool")


def _is_return_destination(source: pd.DataFrame) -> pd.Series:
    return source[RETURN_DESTINATION_COLUMN].map(
        lambda value: (
            (trim_text(value) or "").upper() in RETURN_DESTINATION_CITIES
        ),
        na_action=None,
    ).astype("bool")


def _group_positions(note_keys: pd.Series) -> dict[str | None, list[int]]:
    groups: dict[str | None, list[int]] = {}
    for position, key in enumerate(note_keys):
        groups.setdefault(key, []).append(position)
    return groups


def _distinct_non_null(values: list[str | None]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value is not None))


def _build_return_evidence(source: pd.DataFrame) -> _ReturnEvidence:
    _validate_source(source)
    flag_text = _contains_return_text(source)
    destination_flag = _is_return_destination(source)
    cte_text = source[RETURN_CTE_COLUMN].map(identifier_as_text, na_action=None)
    note_keys = source[RETURN_NOTE_COLUMN].map(identifier_as_text, na_action=None)
    candidate_mask = flag_text | destination_flag
    candidate_cte = cte_text.where(candidate_mask, None).astype("object")

    distinct_cte_count = pd.Series(0, index=source.index, dtype="Int64")
    any_destination = pd.Series(False, index=source.index, dtype="bool")
    any_text = pd.Series(False, index=source.index, dtype="bool")
    grouped_ctes = pd.Series("", index=source.index, dtype="object")

    for positions in _group_positions(note_keys).values():
        ctes = _distinct_non_null([cte_text.iloc[position] for position in positions])
        return_ctes = _distinct_non_null(
            [candidate_cte.iloc[position] for position in positions]
        )
        distinct_cte_count.iloc[positions] = len(ctes)
        any_destination.iloc[positions] = bool(destination_flag.iloc[positions].any())
        any_text.iloc[positions] = bool(flag_text.iloc[positions].any())
        grouped_ctes.iloc[positions] = ", ".join(return_ctes)

    flag = (any_text | ((distinct_cte_count > 1) & any_destination)).astype("bool")
    return _ReturnEvidence(
        flag_text=flag_text,
        destination_flag=destination_flag,
        candidate_cte=candidate_cte,
        distinct_cte_count=distinct_cte_count,
        any_destination=any_destination,
        any_text=any_text,
        grouped_ctes=grouped_ctes,
        flag=flag,
    )


def build_flag_devolucao_nf(source: pd.DataFrame) -> pd.Series:
    """Calcula a Flag Devolução NF após o agrupamento por Nota Fiscal."""
    return _build_return_evidence(source).flag


def build_cte_devolucao(source: pd.DataFrame) -> pd.Series:
    """Retorna os CT-es candidatos agregados somente quando a Flag é verdadeira."""
    evidence = _build_return_evidence(source)
    return evidence.grouped_ctes.where(evidence.flag, None).astype("object")


def build_tipo_cte(document_type: pd.Series, return_flag: pd.Series) -> pd.Series:
    """Substitui o Tipo original por DEVOLUCAO quando a Flag é verdadeira."""
    original = document_type.map(trim_text, na_action=None).astype("object")
    flag = return_flag.reindex(document_type.index).eq(True)
    return original.where(~flag, RETURN_TYPE_LABEL).astype("object")
