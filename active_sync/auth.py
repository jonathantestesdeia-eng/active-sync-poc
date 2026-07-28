"""Autenticação inicial e seleção do contexto operacional."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from .client import ActiveClient
from .exceptions import AuthenticationError, CompanySelectionError


@dataclass(frozen=True, slots=True)
class LoginResult:
    message: str
    session_cookie_received: bool
    discovered_user_code: str | None = None


@dataclass(frozen=True, slots=True)
class ContextResult:
    user_code_source: str
    operational_session_validated: bool


@dataclass(frozen=True, slots=True)
class ContextOption:
    value: str
    label: str


_USER_CODE_KEYS = {
    "_code",
    "usercode",
    "user_code",
    "usuariocodigo",
    "codigo_usuario",
    "codigousuario",
}


def _extract_explicit_user_code(value: object) -> str | None:
    """Busca somente chaves que identifiquem explicitamente o código do usuário."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _USER_CODE_KEYS and item is not None:
                candidate = str(item).strip()
                if candidate:
                    return candidate
        for item in value.values():
            found = _extract_explicit_user_code(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _extract_explicit_user_code(item)
            if found:
                return found
    return None


def login(client: ActiveClient, logger: logging.Logger) -> LoginResult:
    logger.info("Autenticando")
    try:
        response = client.session.post(
            client.url("/SITE/Login/Loging"),
            data={"user": client.settings.user, "password": client.settings.password},
            timeout=client.settings.http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise AuthenticationError(f"Não foi possível conectar ao Active OnSupply: {exc}") from exc

    if response.status_code != 200:
        raise AuthenticationError(
            f"O login retornou HTTP {response.status_code}; era esperado HTTP 200."
        )

    try:
        payload = response.json()
    except (requests.exceptions.JSONDecodeError, ValueError) as exc:
        raise AuthenticationError("A resposta do login não contém um JSON válido.") from exc

    if not isinstance(payload, dict):
        raise AuthenticationError("A resposta do login possui um formato inesperado.")

    if payload.get("Success") is not True:
        message = str(payload.get("Message") or "Login recusado pelo Active OnSupply.")
        raise AuthenticationError(message)

    session_id = client.session.cookies.get("sessionID")
    if not session_id:
        raise AuthenticationError("O cookie sessionID não foi recebido.")

    logger.info("Login inicial concluído")
    logger.info("Cookie de sessão recebido (valor oculto)")
    return LoginResult(
        message=str(payload.get("Message") or "Login concluído."),
        session_cookie_received=True,
        discovered_user_code=_extract_explicit_user_code(payload),
    )


def _response_payload(response: requests.Response) -> object | None:
    try:
        return response.json()
    except (requests.exceptions.JSONDecodeError, ValueError):
        return None


def discover_user_code(client: ActiveClient, login_result: LoginResult) -> tuple[str | None, str]:
    if client.settings.user_code:
        return client.settings.user_code, "ACTIVE_USER_CODE"
    if login_result.discovered_user_code:
        return login_result.discovered_user_code, "resposta do login"

    try:
        response = client.session.get(
            client.url("/SITE/Login/UsuarioNome"),
            timeout=client.settings.http_timeout_seconds,
        )
    except requests.RequestException:
        return None, "não identificado"

    if response.status_code != 200:
        return None, "não identificado"
    discovered = _extract_explicit_user_code(_response_payload(response))
    if discovered:
        return discovered, "endpoint UsuarioNome"
    # O JavaScript público da tela copia #login-password para #login-code-copy,
    # enviado como _code em LogingCompany. O valor nunca deve ser registrado.
    return client.settings.password, "campo de senha da tela de login"


_VALUE_KEYS = (
    "value",
    "cliente_id",
    "filial_id",
    "tipoacesso_id",
    "tipo_acesso_id",
    "id",
    "codigo",
    "code",
    "key",
)
_LABEL_KEYS = (
    "text",
    "label",
    "nomecompleto",
    "nome_completo",
    "nome",
    "name",
    "descricao",
    "description",
    "documento",
)


def _dict_value(item: dict[object, object], names: Iterable[str]) -> str | None:
    normalized = {str(key).strip().lower(): value for key, value in item.items()}
    for name in names:
        value = normalized.get(name)
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return None


def _options_from_json(
    payload: object,
    value_keys: Iterable[str] = _VALUE_KEYS,
    label_keys: Iterable[str] = _LABEL_KEYS,
) -> list[ContextOption]:
    options: list[ContextOption] = []
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return options
        options.extend(_options_from_json(decoded, value_keys, label_keys))
    elif isinstance(payload, list):
        for item in payload:
            options.extend(_options_from_json(item, value_keys, label_keys))
    elif isinstance(payload, dict):
        value = _dict_value(payload, value_keys)
        label = _dict_value(payload, label_keys)
        if value is not None and label is not None:
            options.append(ContextOption(value=value, label=label))
        else:
            for child in payload.values():
                if isinstance(child, (dict, list)):
                    options.extend(_options_from_json(child, value_keys, label_keys))
    return options


def parse_context_options(
    response: requests.Response,
    value_keys: Iterable[str] = _VALUE_KEYS,
    label_keys: Iterable[str] = _LABEL_KEYS,
) -> list[ContextOption]:
    """Lê opções JSON ou HTML sem pressupor que rótulo e valor sejam iguais."""
    payload = _response_payload(response)
    options = _options_from_json(payload, value_keys, label_keys) if payload is not None else []
    if not options:
        soup = BeautifulSoup(str(getattr(response, "text", "") or ""), "html.parser")
        for option in soup.select("option[value]"):
            value = str(option.get("value") or "").strip()
            label = option.get_text(" ", strip=True)
            if value and label:
                options.append(ContextOption(value=value, label=label))

    unique: list[ContextOption] = []
    seen: set[tuple[str, str]] = set()
    for option in options:
        key = (option.value, option.label)
        if key not in seen:
            seen.add(key)
            unique.append(option)
    return unique


def _get_context_options(
    client: ActiveClient,
    path: str,
    *,
    params: dict[str, str] | None = None,
    value_keys: Iterable[str] = _VALUE_KEYS,
    label_keys: Iterable[str] = _LABEL_KEYS,
) -> list[ContextOption]:
    try:
        response = client.session.get(
            client.url(path),
            params=params,
            timeout=client.settings.http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise CompanySelectionError(f"Falha ao consultar {path}: {exc}") from exc
    if response.status_code != 200:
        raise CompanySelectionError(f"A consulta {path} retornou HTTP {response.status_code}.")
    if _is_login_page(response):
        raise CompanySelectionError("A sessão retornou para a tela de login durante a descoberta.")
    return parse_context_options(response, value_keys, label_keys)


def list_available_contexts(
    client: ActiveClient,
    login_result: LoginResult,
    logger: logging.Logger,
    company_id: str | None = None,
) -> None:
    """Lista os valores reais enviados pelos seletores, sem alterar o contexto."""
    companies = _get_context_options(client, "/SITE/Login/Company")
    if not companies:
        raise CompanySelectionError("O endpoint Company não retornou opções reconhecíveis.")

    logger.info("Empresas disponíveis (valor enviado | texto exibido):")
    for option in companies:
        logger.info("  %s | %s", option.value, option.label)

    selected_company = company_id
    if selected_company is None and len(companies) == 1:
        selected_company = companies[0].value
        logger.info("Empresa única selecionada apenas para consultar filial e acesso")
    if selected_company is None:
        logger.info("Há múltiplas empresas; repita com --company-id VALOR para listar filiais")
    else:
        valid_values = {option.value for option in companies}
        if selected_company not in valid_values:
            raise CompanySelectionError("O valor informado em --company-id não está na lista retornada.")
        branches = _get_context_options(
            client, "/SITE/Login/Filial", params={"empresa": selected_company}
        )
        access_types = _get_context_options(
            client,
            "/SITE/Login/TiposAcesso",
            params={"empresa": selected_company},
            value_keys=("sigla",),
            label_keys=("tipoacesso",),
        )
        logger.info("Filiais disponíveis (valor enviado | texto exibido):")
        for option in branches:
            logger.info("  %s | %s", option.value, option.label)
        logger.info("Tipos de acesso disponíveis (valor enviado | texto exibido):")
        for option in access_types:
            logger.info("  %s | %s", option.value, option.label)

    user_code, source = discover_user_code(client, login_result)
    if user_code:
        logger.info("Valor de _code identificado (%s; valor oculto)", source)
    else:
        logger.info("Valor de _code não identificado automaticamente")


def _is_login_page(response: requests.Response) -> bool:
    final_url = str(getattr(response, "url", "") or "").lower().rstrip("/")
    redirected_to_login = bool(getattr(response, "history", [])) and final_url.endswith("/site/login")
    text = str(getattr(response, "text", "") or "").lower()
    has_password_form = "name=\"password\"" in text or "name='password'" in text
    has_login_form = has_password_form and ("/site/login/loging" in text or "type=\"password\"" in text)
    return redirected_to_login or has_login_form


def select_company_context(
    client: ActiveClient,
    login_result: LoginResult,
    logger: logging.Logger,
) -> ContextResult:
    client.settings.validate_context()
    user_code, code_source = discover_user_code(client, login_result)
    if not user_code:
        raise CompanySelectionError(
            "O código do usuário não pôde ser obtido automaticamente. "
            "Preencha ACTIVE_USER_CODE no arquivo .env."
        )

    logger.info("Selecionando empresa, filial e tipo de acesso")
    data = {
        "_user": client.settings.user,
        "_code": user_code,
        "_company": client.settings.company_id,
        "_filial": client.settings.branch_id,
        "_type": client.settings.access_type,
        "_isDestinatario": str(client.settings.is_destinatario).lower(),
        "company": client.settings.company_id,
        "company-filial": client.settings.branch_id,
        "company-filial-type": client.settings.access_type,
    }
    try:
        response = client.session.post(
            client.url("/SITE/Login/LogingCompany"),
            data=data,
            timeout=client.settings.http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise CompanySelectionError(
            f"Não foi possível selecionar empresa e filial: {exc}"
        ) from exc

    if response.status_code != 200:
        raise CompanySelectionError(
            f"A seleção de empresa e filial retornou HTTP {response.status_code}."
        )

    payload = _response_payload(response)
    if isinstance(payload, dict) and payload.get("Success") is False:
        raise CompanySelectionError(
            str(payload.get("Message") or "A empresa ou filial configurada não foi aceita.")
        )
    if _is_login_page(response):
        raise CompanySelectionError("A empresa ou filial configurada não foi aceita.")

    validate_operational_session(client)
    logger.info("Empresa, filial e tipo de acesso selecionados")
    logger.info("Sessão operacional validada")
    logger.info("Valor de _code obtido de: %s (valor oculto)", code_source)
    return ContextResult(user_code_source=code_source, operational_session_validated=True)


def validate_operational_session(client: ActiveClient) -> None:
    """Valida a sessão em uma rota protegida sem criar um relatório."""
    try:
        response = client.session.post(
            client.url("/SITE/Relatorio/Grid_RelatoriosAssincronos"),
            params={"formularioID": client.settings.formulario_id, "view": "null"},
            timeout=client.settings.http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise CompanySelectionError(
            f"Não foi possível validar a sessão operacional: {exc}"
        ) from exc

    if response.status_code != 200:
        raise CompanySelectionError(
            f"A validação da sessão operacional retornou HTTP {response.status_code}."
        )
    if _is_login_page(response):
        raise CompanySelectionError(
            "A sessão retornou para a tela de login após selecionar o contexto."
        )

    text = str(getattr(response, "text", "") or "").lower()
    expected_html = any(marker in text for marker in ("<table", "<tbody", "<tr", "relatorio"))
    if not expected_html:
        raise CompanySelectionError(
            "A rota protegida respondeu, mas o conteúdo não confirmou uma sessão operacional."
        )
