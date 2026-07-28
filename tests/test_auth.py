from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest
import requests

from active_sync.auth import (
    ContextOption,
    LoginResult,
    login,
    parse_context_options,
    select_company_context,
)
from active_sync.client import ActiveClient
from active_sync.config import Settings
from active_sync.exceptions import AuthenticationError, CompanySelectionError


def settings(*, user_code: str | None = None) -> Settings:
    return Settings(
        base_url="https://exemplo.invalid",
        user="usuario-de-teste",
        password="segredo-de-teste",
        user_code=user_code,
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


def mock_client(payload: dict, *, with_cookie: bool = True) -> ActiveClient:
    session = requests.Session()
    response = Mock(status_code=200)
    response.json.return_value = payload
    session.post = Mock(return_value=response)  # type: ignore[method-assign]
    if with_cookie:
        session.cookies.set("sessionID", "cookie-secreto-de-teste")
    return ActiveClient(settings(), session=session)


def test_successful_login_requires_session_cookie() -> None:
    client = mock_client({"Success": True, "Message": "OK"})

    result = login(client, logging.getLogger("test"))

    assert result.session_cookie_received is True
    sent = client.session.post.call_args.kwargs["data"]  # type: ignore[attr-defined]
    assert sent == {"user": "usuario-de-teste", "password": "segredo-de-teste"}


def test_login_rejected() -> None:
    client = mock_client({"Success": False, "Message": "Credenciais inválidas"})

    with pytest.raises(AuthenticationError, match="Credenciais inválidas"):
        login(client, logging.getLogger("test"))


def test_missing_session_cookie_is_rejected() -> None:
    client = mock_client({"Success": True, "Message": "OK"}, with_cookie=False)

    with pytest.raises(AuthenticationError, match="sessionID"):
        login(client, logging.getLogger("test"))


def response(*, payload: dict | None = None, text: str = "", url: str = "") -> Mock:
    item = Mock(status_code=200, text=text, url=url, history=[])
    if payload is None:
        item.json.side_effect = ValueError("sem JSON")
    else:
        item.json.return_value = payload
    return item


def context_client(*, protected_text: str = "<table><tbody></tbody></table>") -> ActiveClient:
    session = requests.Session()
    session.get = Mock(return_value=response(payload={"CodigoUsuario": "codigo-descoberto"}))  # type: ignore[method-assign]
    session.post = Mock(  # type: ignore[method-assign]
        side_effect=[
            response(payload={"Success": True, "Message": "OK"}),
            response(text=protected_text),
        ]
    )
    return ActiveClient(settings(), session=session)


def test_selects_company_and_validates_protected_route() -> None:
    client = context_client()
    login_result = LoginResult("OK", True)

    result = select_company_context(client, login_result, logging.getLogger("test"))

    assert result.operational_session_validated is True
    selection_data = client.session.post.call_args_list[0].kwargs["data"]  # type: ignore[attr-defined]
    assert selection_data["_code"] == "codigo-descoberto"
    assert selection_data["_company"] == "empresa-teste"
    assert selection_data["_filial"] == "filial-teste"
    assert selection_data["_isDestinatario"] == "false"


def test_rejected_company_selection() -> None:
    client = context_client()
    client.session.post = Mock(  # type: ignore[method-assign]
        return_value=response(payload={"Success": False, "Message": "Contexto recusado"})
    )

    with pytest.raises(CompanySelectionError, match="Contexto recusado"):
        select_company_context(client, LoginResult("OK", True), logging.getLogger("test"))


def test_operational_validation_rejects_login_page() -> None:
    login_html = '<form action="/SITE/Login/Loging"><input name="password" type="password"></form>'
    client = context_client(protected_text=login_html)

    with pytest.raises(CompanySelectionError, match="retornou para a tela de login"):
        select_company_context(client, LoginResult("OK", True), logging.getLogger("test"))


def test_password_is_used_as_code_when_endpoint_does_not_provide_one() -> None:
    session = requests.Session()
    session.get = Mock(return_value=response(payload={"Nome": "Usuário de teste"}))  # type: ignore[method-assign]
    session.post = Mock(  # type: ignore[method-assign]
        side_effect=[
            response(payload={"Success": True}),
            response(text="<table><tbody></tbody></table>"),
        ]
    )
    client = ActiveClient(settings(), session=session)

    select_company_context(client, LoginResult("OK", True), logging.getLogger("test"))

    selection_data = session.post.call_args_list[0].kwargs["data"]
    assert selection_data["_code"] == "segredo-de-teste"


def test_parses_context_options_from_json() -> None:
    item = response(payload=[{"Value": "interno-42", "Text": "00.000.000/0001-00 - Empresa"}])

    options = parse_context_options(item)

    assert options[0].value == "interno-42"
    assert options[0].label == "00.000.000/0001-00 - Empresa"


def test_parses_context_options_from_html() -> None:
    item = response(text='<select><option value="filial-7">Filial visível</option></select>')

    options = parse_context_options(item)

    assert options[0].value == "filial-7"
    assert options[0].label == "Filial visível"


def test_parses_double_encoded_active_company_json() -> None:
    encoded = '[{"Cliente_ID":2063391,"Documento":"00000000000000","NomeCompleto":"Empresa de teste"}]'
    item = response(payload=encoded)

    options = parse_context_options(item)

    assert options == [ContextOption(value="2063391", label="Empresa de teste")]


def test_parses_active_access_type_with_endpoint_specific_fields() -> None:
    encoded = '[{"Cliente_ID":2063391,"Sigla":"C","TipoAcesso":"CONTRATANTE"}]'
    item = response(payload=encoded)

    options = parse_context_options(item, value_keys=("sigla",), label_keys=("tipoacesso",))

    assert options == [ContextOption(value="C", label="CONTRATANTE")]
