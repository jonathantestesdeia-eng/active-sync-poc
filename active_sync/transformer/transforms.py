"""Normalizadores reutilizáveis e transformação principal do DataFrame."""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from active_sync.exceptions import TransformationValidationError

from .columns import DATE_COLUMNS, NUMERIC_COLUMNS, OUTPUT_COLUMNS
from .mapping import (
    CLIENT_LOOKUP_CNPJ_COLUMN,
    CLIENT_LOOKUP_CODE_COLUMN,
    COLUMN_MAPPING,
    DEFAULT_TRANSPORTADORA,
    PRAZO_DELIVERY_COLUMN,
    PRAZO_FORECAST_COLUMN,
    PRAZO_LATE,
    PRAZO_ON_TIME,
    PRAZO_RETURNED,
    PRAZO_WITHOUT_DELIVERY,
    PRAZO_WITHOUT_FORECAST,
    TRANSPORTADORA_MAPPING,
)
from .normalization import (
    identifier_as_text,
    normalize_null,
    normalize_text_series,
    safe_date_series,
    safe_number_series,
    trim_text,
)
from .returns import build_cte_devolucao, build_flag_devolucao_nf, build_tipo_cte
from .situation import build_situacao
from .validator import validate_output_dataframe, validate_source_dataframe


PORTUGUESE_MONTH_NAMES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _extract_cnpj(value: Any) -> str | None:
    """Extrai o identificador numérico anterior ao nome do Destinatário."""
    text = trim_text(value)
    if text is None:
        return None
    prefix = text.split(" - ", 1)[0]
    digits = re.sub(r"\D", "", prefix)
    if not digits:
        return None
    # A referência Power Query remove zeros iniciais antes de devolver texto.
    return digits.lstrip("0") or "0"


def build_cnpj(recipient: pd.Series) -> pd.Series:
    """Reproduz o CNPJ do Power Query a partir da coluna Destinatário."""
    return recipient.map(_extract_cnpj, na_action=None).astype("object")


def _extract_recipient_name(value: Any) -> str | None:
    """Retorna a segunda parte gerada pelo split do Power Query por hífen."""
    text = trim_text(value)
    if text is None:
        return None
    parts = text.split("-", 2)
    if len(parts) < 2:
        return None
    return trim_text(parts[1])


def build_destinatario(recipient: pd.Series) -> pd.Series:
    """Reproduz o nome do destinatário extraído pelo Power Query."""
    return recipient.map(_extract_recipient_name, na_action=None).astype("object")


def build_codigo_cliente(
    cnpj: pd.Series,
    client_register: pd.DataFrame,
) -> pd.Series:
    """Busca o código do cliente pelo CNPJ na mesma tabela cadastral do Power Query."""
    required = {CLIENT_LOOKUP_CNPJ_COLUMN, CLIENT_LOOKUP_CODE_COLUMN}
    missing = sorted(required - set(str(column) for column in client_register.columns))
    if missing:
        raise TransformationValidationError(
            "O cadastro de clientes não contém colunas obrigatórias: "
            f"{missing}."
        )

    lookup_keys = build_cnpj(
        client_register[CLIENT_LOOKUP_CNPJ_COLUMN].map(
            identifier_as_text,
            na_action=None,
        )
    )
    populated_keys = lookup_keys.dropna()
    duplicated_keys = populated_keys[populated_keys.duplicated(keep=False)].unique()
    if len(duplicated_keys):
        raise TransformationValidationError(
            "O cadastro de clientes contém CNPJ duplicado e não permite uma busca "
            f"determinística: {duplicated_keys.tolist()}."
        )

    lookup_values = client_register[CLIENT_LOOKUP_CODE_COLUMN].map(
        identifier_as_text,
        na_action=None,
    )
    lookup = dict(zip(lookup_keys, lookup_values, strict=True))
    normalized_cnpj = cnpj.map(identifier_as_text, na_action=None)
    return normalized_cnpj.map(lookup).map(normalize_null, na_action=None).astype("object")


def _map_carrier(value: Any) -> str | None:
    """Aplica a primeira correspondência textual definida pelo Power Query."""
    text = trim_text(value)
    if text is None:
        return None
    normalized = text.upper()
    for token, carrier in TRANSPORTADORA_MAPPING:
        if token in normalized:
            return carrier
    return DEFAULT_TRANSPORTADORA


def build_transportadora(carrier: pd.Series) -> pd.Series:
    """Normaliza o transportador bruto para a transportadora operacional."""
    return carrier.map(_map_carrier, na_action=None).astype("object")


def build_entrega(delivery: pd.Series) -> pd.Series:
    """Converte a data de entrega bruta sem introduzir regras de negócio."""
    return safe_date_series(delivery)


def build_data(delivery: pd.Series) -> pd.Series:
    """Retorna o mês da Entrega em português minúsculo e independente de locale."""
    parsed = safe_date_series(delivery)
    return parsed.dt.month.map(
        lambda month: (
            PORTUGUESE_MONTH_NAMES[int(month) - 1]
            if pd.notna(month)
            else None
        )
    ).astype("object")


def build_ano(delivery: pd.Series) -> pd.Series:
    """Retorna o ano inteiro da Entrega usando o tipo anulável do pandas."""
    return safe_date_series(delivery).dt.year.astype("Int64")


def _build_deadline_status(delivery: pd.Series, forecast: pd.Series) -> pd.Series:
    """Classifica a entrega contra a previsão usando apenas a data civil."""
    parsed_delivery = safe_date_series(delivery).dt.normalize()
    parsed_forecast = safe_date_series(forecast.reindex(delivery.index)).dt.normalize()
    result = pd.Series([None] * len(delivery), index=delivery.index, dtype="object")
    without_delivery = parsed_delivery.isna()
    without_forecast = parsed_delivery.notna() & parsed_forecast.isna()
    comparable = parsed_delivery.notna() & parsed_forecast.notna()
    result.loc[without_delivery] = PRAZO_WITHOUT_DELIVERY
    result.loc[without_forecast] = PRAZO_WITHOUT_FORECAST
    result.loc[comparable & (parsed_delivery <= parsed_forecast)] = PRAZO_ON_TIME
    result.loc[comparable & (parsed_delivery > parsed_forecast)] = PRAZO_LATE
    return result


def build_prazo(
    delivery: pd.Series,
    forecast: pd.Series,
    return_flag: pd.Series | None = None,
) -> pd.Series:
    """Classifica o prazo, priorizando a devolução conforme a consulta M."""
    result = _build_deadline_status(delivery, forecast)
    if return_flag is not None:
        result.loc[return_flag.reindex(delivery.index).eq(True)] = PRAZO_RETURNED
    return result


def build_prazo2(delivery: pd.Series, forecast: pd.Series) -> pd.Series:
    """Reproduz o segundo status de prazo, idêntico ao primeiro na referência."""
    return _build_deadline_status(delivery, forecast)


def transform_dataframe(
    source: pd.DataFrame,
    logger: logging.Logger | None = None,
    client_register: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Transforma o relatório bruto no contrato inicial de Performance Entrega."""
    source_validation = validate_source_dataframe(source)
    if not source_validation.is_valid:
        raise TransformationValidationError("; ".join(source_validation.errors))

    result = pd.DataFrame(index=source.index)
    for output_column in OUTPUT_COLUMNS:
        source_column = COLUMN_MAPPING[output_column]
        if output_column == "Código cliente":
            if client_register is None:
                result[output_column] = pd.Series(
                    [None] * len(source),
                    index=source.index,
                    dtype="object",
                )
            else:
                result[output_column] = build_codigo_cliente(
                    result["CNPJ"],
                    client_register,
                )
        elif output_column == "CNPJ":
            result[output_column] = build_cnpj(source[source_column])
        elif output_column == "Destinatário":
            result[output_column] = build_destinatario(source[source_column])
        elif output_column == "Transportadora":
            result[output_column] = build_transportadora(source[source_column])
        elif output_column == "Flag Devolução NF":
            result[output_column] = build_flag_devolucao_nf(source)
        elif output_column == "Tipo CTe":
            result[output_column] = build_tipo_cte(
                source[source_column],
                result["Flag Devolução NF"],
            )
        elif output_column == "CTe Devolução":
            result[output_column] = build_cte_devolucao(source)
        elif output_column == "Entrega":
            result[output_column] = build_entrega(source[source_column])
        elif output_column == "Data":
            result[output_column] = build_data(source[source_column])
        elif output_column == "Ano":
            result[output_column] = build_ano(source[source_column])
        elif output_column == "Prazo":
            result[output_column] = build_prazo(
                source[PRAZO_DELIVERY_COLUMN],
                source[PRAZO_FORECAST_COLUMN],
                result["Flag Devolução NF"],
            )
        elif output_column == "Prazo2":
            result[output_column] = build_prazo2(
                source[PRAZO_DELIVERY_COLUMN],
                source[PRAZO_FORECAST_COLUMN],
            )
        elif output_column == "Data3":
            result[output_column] = result["Data"].copy()
        elif output_column == "Ano4":
            result[output_column] = result["Ano"].copy()
        elif output_column == "Situação":
            result[output_column] = build_situacao(
                result["Flag Devolução NF"],
                source[PRAZO_DELIVERY_COLUMN],
                source[PRAZO_FORECAST_COLUMN],
            )
        elif output_column in DATE_COLUMNS:
            result[output_column] = safe_date_series(source[source_column])
        elif output_column in NUMERIC_COLUMNS:
            result[output_column] = safe_number_series(source[source_column])
        else:
            result[output_column] = normalize_text_series(source[source_column])

    result = result.loc[:, list(OUTPUT_COLUMNS)]
    output_validation = validate_output_dataframe(result)
    if not output_validation.is_valid:
        raise TransformationValidationError("; ".join(output_validation.errors))
    if logger:
        logger.info(
            "Transformação concluída: %d registros e %d colunas",
            len(result),
            len(result.columns),
        )
    return result
