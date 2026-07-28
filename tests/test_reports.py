from __future__ import annotations

from datetime import date
import json
import logging
from unittest.mock import Mock

import pytest
import requests

from active_sync.client import ActiveClient
from active_sync.config import Settings
from active_sync.exceptions import ConfigError, ReportRequestError
from active_sync.reports import request_report, resolve_report_window


def settings() -> Settings:
    return Settings(
        base_url="https://exemplo.invalid",
        user="usuario-teste",
        password="segredo-teste",
        user_code=None,
        company_id="empresa-teste",
        branch_id="filial-teste",
        access_type="C",
        is_destinatario=False,
        formulario_id=118,
        report_code="118",
        report_name="Conhecimento - CTe",
        report_format="Excel__NotaFiscal",
        date_from=None,
        date_to=None,
        poll_interval_seconds=10,
        report_timeout_seconds=900,
        http_timeout_seconds=60,
        report_time_tolerance_seconds=120,
    )


def test_resolves_cli_dates() -> None:
    window = resolve_report_window(
        "20/07/2026", "21/07/2026", None, None, today=date(2026, 7, 22)
    )

    assert window.formatted_from == "20/07/2026"
    assert window.formatted_to == "21/07/2026"


def test_empty_dates_use_current_date() -> None:
    window = resolve_report_window(None, None, None, None, today=date(2026, 7, 21))

    assert window.formatted_from == "21/07/2026"
    assert window.formatted_to == "21/07/2026"


def test_rejects_large_or_reversed_range() -> None:
    with pytest.raises(ConfigError, match="máximo"):
        resolve_report_window("01/07/2026", "10/07/2026", None, None)
    with pytest.raises(ConfigError, match="posterior"):
        resolve_report_window("22/07/2026", "21/07/2026", None, None)


def test_requests_report_with_exact_filters() -> None:
    session = requests.Session()
    response = Mock(status_code=200)
    response.json.return_value = {"Success": True, "Message": "Será processado."}
    session.post = Mock(return_value=response)  # type: ignore[method-assign]
    client = ActiveClient(settings(), session=session)
    window = resolve_report_window("20/07/2026", "21/07/2026", None, None)

    result = request_report(client, window, logging.getLogger("test"))

    assert result.message == "Será processado."
    call = session.post.call_args
    assert call.kwargs["params"]["codigo"] == "118"
    assert call.kwargs["params"]["nomeArquivoOrigem"] == "#nomeArquivo"
    filters = json.loads(call.kwargs["data"]["filtro"])
    assert filters[0]["Campo"] == "Filtro_Data_Emissao_De"
    assert filters[0]["Valor"] == "20/07/2026"
    assert filters[1]["Campo"] == "Filtro_Data_Emissao_Ate"
    assert filters[1]["Valor"] == "21/07/2026"


def test_rejected_report_request() -> None:
    session = requests.Session()
    response = Mock(status_code=200)
    response.json.return_value = {"Success": False, "Message": "Solicitação recusada"}
    session.post = Mock(return_value=response)  # type: ignore[method-assign]
    client = ActiveClient(settings(), session=session)
    window = resolve_report_window("21/07/2026", "21/07/2026", None, None)

    with pytest.raises(ReportRequestError, match="Solicitação recusada"):
        request_report(client, window, logging.getLogger("test"))


def test_internal_server_error_is_marked_as_possibly_queued() -> None:
    session = requests.Session()
    response = Mock(status_code=200)
    response.json.return_value = {"Success": False, "Message": "Internal Server Error"}
    session.post = Mock(return_value=response)  # type: ignore[method-assign]
    client = ActiveClient(settings(), session=session)
    window = resolve_report_window("21/07/2026", "21/07/2026", None, None)

    result = request_report(client, window, logging.getLogger("test"))

    assert result.accepted is False
