"""Solicitação controlada de relatórios assíncronos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import logging

import requests

from .client import ActiveClient
from .exceptions import ConfigError, ReportRequestError


DATE_FORMAT = "%d/%m/%Y"
MAX_REPORT_RANGE_DAYS = 7


@dataclass(frozen=True, slots=True)
class ReportWindow:
    date_from: date
    date_to: date

    @property
    def formatted_from(self) -> str:
        return self.date_from.strftime(DATE_FORMAT)

    @property
    def formatted_to(self) -> str:
        return self.date_to.strftime(DATE_FORMAT)


@dataclass(frozen=True, slots=True)
class ReportRequestResult:
    message: str
    accepted: bool
    local_before: datetime
    local_after: datetime
    utc_before: datetime
    utc_after: datetime


def _parse_date(value: str, variable_name: str) -> date:
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError as exc:
        raise ConfigError(f"{variable_name} deve estar no formato DD/MM/AAAA.") from exc


def resolve_report_window(
    cli_date_from: str | None,
    cli_date_to: str | None,
    env_date_from: str | None,
    env_date_to: str | None,
    *,
    today: date | None = None,
) -> ReportWindow:
    current_date = today or datetime.now().astimezone().date()
    raw_from = cli_date_from or env_date_from
    raw_to = cli_date_to or env_date_to
    date_from = _parse_date(raw_from, "Data inicial") if raw_from else current_date
    date_to = _parse_date(raw_to, "Data final") if raw_to else current_date

    if date_from > date_to:
        raise ConfigError("A data inicial não pode ser posterior à data final.")
    range_days = (date_to - date_from).days + 1
    if range_days > MAX_REPORT_RANGE_DAYS:
        raise ConfigError(
            f"O intervalo da POC deve ter no máximo {MAX_REPORT_RANGE_DAYS} dias."
        )
    return ReportWindow(date_from=date_from, date_to=date_to)


def build_report_filters(window: ReportWindow) -> list[dict[str, object]]:
    return [
        {
            "Campo": "Filtro_Data_Emissao_De",
            "Tipo": "System.DateTime",
            "Operador": "=",
            "Valor": window.formatted_from,
            "ComboValor": None,
        },
        {
            "Campo": "Filtro_Data_Emissao_Ate",
            "Tipo": "System.DateTime",
            "Operador": "=",
            "Valor": window.formatted_to,
            "ComboValor": None,
        },
    ]


def confirm_report_request(window: ReportWindow, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(
        f"Gerar relatório de {window.formatted_from} até {window.formatted_to}? "
        "Digite SIM para confirmar: "
    )
    return answer.strip().casefold() == "sim"


def request_report(
    client: ActiveClient,
    window: ReportWindow,
    logger: logging.Logger,
) -> ReportRequestResult:
    params = {
        "relatorioTipo": "Modulo_Relatorio",
        "nomeArquivoOrigem": "#nomeArquivo",
        "codigoOrigem": "#itemCodigo",
        "nomeArquivo": client.settings.report_name,
        "codigo": client.settings.report_code,
        "relatorio": "true",
        "formato": client.settings.report_format,
    }
    data = {
        "filtro": json.dumps(build_report_filters(window), ensure_ascii=False),
        "formato": client.settings.report_format,
        "apenasNaoImpresso": "false",
        "visaoRelatorio": "Padrão",
    }

    local_before = datetime.now().astimezone()
    utc_before = datetime.now(timezone.utc)
    logger.info("Horário antes do disparo — local: %s", local_before.isoformat())
    logger.info("Horário antes do disparo — UTC: %s", utc_before.isoformat())
    logger.info(
        "Solicitando relatório: %s até %s", window.formatted_from, window.formatted_to
    )
    try:
        response = client.session.post(
            client.url("/SITE/Relatorio/ProcessaArquivo/"),
            params=params,
            data=data,
            timeout=client.settings.http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise ReportRequestError(f"Não foi possível solicitar o relatório: {exc}") from exc
    finally:
        local_after = datetime.now().astimezone()
        utc_after = datetime.now(timezone.utc)

    logger.info("Horário após o disparo — local: %s", local_after.isoformat())
    logger.info("Horário após o disparo — UTC: %s", utc_after.isoformat())

    if response.status_code != 200:
        raise ReportRequestError(
            f"A solicitação do relatório retornou HTTP {response.status_code}."
        )
    try:
        payload = response.json()
    except (requests.exceptions.JSONDecodeError, ValueError) as exc:
        raise ReportRequestError("A resposta da solicitação não contém um JSON válido.") from exc
    if not isinstance(payload, dict):
        raise ReportRequestError("A resposta da solicitação possui um formato inesperado.")
    accepted = payload.get("Success") is True
    if not accepted:
        failure_message = str(
            payload.get("Message") or "O Active OnSupply recusou a solicitação do relatório."
        )
        if "internal server error" not in failure_message.casefold():
            raise ReportRequestError(failure_message)
        logger.warning(
            "O Active respondeu Internal Server Error; a grade será consultada antes de qualquer nova tentativa"
        )

    message = str(payload.get("Message") or "Relatório solicitado.")
    if accepted:
        logger.info("Relatório solicitado com sucesso")
    return ReportRequestResult(
        message=message,
        accepted=accepted,
        local_before=local_before,
        local_after=local_after,
        utc_before=utc_before,
        utc_after=utc_after,
    )
