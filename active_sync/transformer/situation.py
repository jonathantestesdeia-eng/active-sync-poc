"""Construção da Situação Active conforme a consulta M oficial."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from .mapping import (
    SITUACAO_DELIVERED,
    SITUACAO_DUE_TODAY,
    SITUACAO_LATE,
    SITUACAO_OPEN,
    SITUACAO_RETURNED,
    SITUACAO_WITHOUT_FORECAST,
)
from .normalization import safe_date_series


def _reference_day(value: date | datetime | pd.Timestamp | None) -> pd.Timestamp:
    """Converte o momento da atualização na data civil usada pelo Power Query."""
    return pd.Timestamp(value if value is not None else datetime.now()).normalize()


def build_situacao(
    return_flag: pd.Series,
    delivery: pd.Series,
    forecast: pd.Series,
    reference_date: date | datetime | pd.Timestamp | None = None,
) -> pd.Series:
    """Reproduz `Situação Active` preservando a precedência da consulta M."""
    parsed_delivery = safe_date_series(delivery).dt.normalize()
    parsed_forecast = safe_date_series(forecast.reindex(delivery.index)).dt.normalize()
    returned = return_flag.reindex(delivery.index).eq(True)
    today = _reference_day(reference_date)

    result = pd.Series(SITUACAO_OPEN, index=delivery.index, dtype="object")
    not_delivered = parsed_delivery.isna()
    result.loc[not_delivered & (parsed_forecast < today)] = SITUACAO_LATE
    result.loc[not_delivered & (parsed_forecast == today)] = SITUACAO_DUE_TODAY
    result.loc[not_delivered & parsed_forecast.isna()] = SITUACAO_WITHOUT_FORECAST
    result.loc[parsed_delivery.notna()] = SITUACAO_DELIVERED
    result.loc[returned] = SITUACAO_RETURNED
    return result
