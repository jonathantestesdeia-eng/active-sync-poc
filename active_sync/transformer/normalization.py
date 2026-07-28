"""Normalizadores independentes compartilhados pela camada de transformação."""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd


NULL_TEXTS = frozenset({"", "none", "null", "nan", "nat", "<na>"})


def normalize_null(value: Any) -> Any | None:
    """Converte valores nulos conhecidos em None sem alterar valores válidos."""
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and value.strip().casefold() in NULL_TEXTS:
        return None
    return value


def trim_text(value: Any) -> str | None:
    """Normaliza nulos e remove espaços laterais de textos."""
    normalized = normalize_null(value)
    if normalized is None:
        return None
    text = str(normalized).strip()
    return text or None


def preserve_identifier(value: Any) -> str | None:
    """Preserva identificadores como texto, inclusive zeros à esquerda."""
    return trim_text(value)


def identifier_as_text(value: Any) -> str | None:
    """Converte identificadores numéricos em texto sem perder zeros textuais."""
    normalized = normalize_null(value)
    if normalized is None:
        return None
    if isinstance(normalized, int) and not isinstance(normalized, bool):
        return str(normalized)
    if isinstance(normalized, float) and math.isfinite(normalized) and normalized.is_integer():
        return str(int(normalized))
    return trim_text(normalized)


def safe_date_series(series: pd.Series) -> pd.Series:
    """Converte uma série em datetime, usando NaT para valores inválidos."""
    normalized = series.map(normalize_null)
    return pd.to_datetime(normalized, errors="coerce", format="mixed", dayfirst=True)


def _normalize_number_text(value: Any) -> Any | None:
    normalized = normalize_null(value)
    if normalized is None or isinstance(normalized, (int, float)):
        return normalized
    text = re.sub(r"[^0-9,\.\-+]", "", str(normalized).strip())
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    return text


def safe_number_series(series: pd.Series) -> pd.Series:
    """Converte números de forma tolerante a formatos decimal BR e internacional."""
    normalized = series.map(_normalize_number_text)
    return pd.to_numeric(normalized, errors="coerce").astype("Float64")


def normalize_text_series(series: pd.Series) -> pd.Series:
    """Aplica trim, nulos e preservação textual a uma série."""
    return series.map(preserve_identifier, na_action=None).astype("object")
