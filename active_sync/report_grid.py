"""Parser e polling da grade de relatórios assíncronos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

from .client import ActiveClient
from .exceptions import (
    ReportAmbiguityError,
    ReportRequestError,
    ReportTimeoutError,
)


GRID_DATE_FORMAT = "%d/%m/%Y %H:%M:%S"
EXCEL_FORMAT_LABEL = "Planilha Excel com Nota Fiscal"


@dataclass(frozen=True, slots=True)
class ReportRow:
    report_id: str | None
    name: str
    report_format: str
    user: str
    requested_at: datetime | None
    download_url: str | None
    status: str


def _cell_text(cells: list[object], index: int) -> str:
    if index >= len(cells):
        return ""
    return cells[index].get_text(" ", strip=True)  # type: ignore[union-attr]


def parse_report_grid(html: str, base_url: str = "") -> list[ReportRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[ReportRow] = []
    for tr in soup.select("tr"):
        cells = tr.find_all("td")
        if len(cells) < 6:
            continue
        id_element = tr.select_one("[data-id]")
        report_id = str(id_element.get("data-id") or "").strip() if id_element else None
        report_id = report_id or None
        name = _cell_text(cells, 1)
        report_format = _cell_text(cells, 2)
        user = _cell_text(cells, 3)
        raw_date = _cell_text(cells, 5)
        try:
            requested_at = datetime.strptime(raw_date, GRID_DATE_FORMAT)
        except ValueError:
            requested_at = None

        download = tr.select_one("a.ico-downloadGrid[href]")
        raw_href = str(download.get("href") or "").strip() if download else ""
        download_url = urljoin(base_url.rstrip("/") + "/", raw_href) if raw_href else None
        row_text = tr.get_text(" ", strip=True).casefold()
        visible_titles = []
        for element in tr.select("[title]"):
            style = str(element.get("style") or "").replace(" ", "").casefold()
            if "display:none" not in style:
                visible_titles.append(str(element.get("title") or "").casefold())
        has_processing_error = any(
            "erro ao processar" in title for title in visible_titles
        )
        has_timeout_or_limit = any(
            "demorou mais de 30 minutos" in title
            or "processo cancelado" in title
            or "ultrapassa o limite" in title
            for title in visible_titles
        )
        explicitly_cancelled = (
            ("cancelado" in row_text or "cancelled" in row_text)
            and "cancelar relatório" not in row_text
        )
        if has_processing_error or has_timeout_or_limit:
            status = "erro"
            download_url = None
        elif explicitly_cancelled:
            status = "cancelado"
            download_url = None
        elif download_url:
            status = "concluído"
        else:
            status = "processando"
        row = ReportRow(
            report_id=report_id,
            name=name,
            report_format=report_format,
            user=user,
            requested_at=requested_at,
            download_url=download_url,
            status=status,
        )
        rows.append(row)
        logging.getLogger("active_sync.api").info(
            "GRID_ROW id=%s file=%s user=%s status=%s format=%s "
            "requested_raw=%s requested_parsed=%s",
            row.report_id or "",
            row.name,
            row.user,
            row.status,
            row.report_format,
            raw_date,
            row.requested_at.isoformat() if row.requested_at else "",
        )
    return rows


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def select_current_report(
    rows: list[ReportRow],
    *,
    report_name: str,
    report_format: str,
    user: str,
    trigger_local: datetime,
    tolerance_seconds: int,
) -> ReportRow | None:
    trigger_naive = trigger_local.replace(tzinfo=None)
    accepted_formats = {_normalized(report_format), _normalized(EXCEL_FORMAT_LABEL)}
    candidates: list[tuple[float, ReportRow]] = []
    discarded = {
        "name": 0,
        "user": 0,
        "format": 0,
        "status": 0,
        "requested_at": 0,
        "time": 0,
    }
    for row in rows:
        logging.getLogger("active_sync.api").info("CHECK_ROW id=%s", row.report_id or "")
        if row.status == "cancelado":
            discarded["status"] += 1
            logging.getLogger("active_sync.api").info(
                "CHECK_ROW id=%s discard=status", row.report_id or ""
            )
            continue
        if row.requested_at is None:
            discarded["requested_at"] += 1
            logging.getLogger("active_sync.api").info(
                "CHECK_ROW id=%s discard=requested_at_none", row.report_id or ""
            )
            continue
        if not row.name.startswith(f"{report_name}_"):
            discarded["name"] += 1
            logging.getLogger("active_sync.api").info(
                "CHECK_ROW id=%s discard=name", row.report_id or ""
            )
            continue
        if _normalized(row.report_format) not in accepted_formats:
            discarded["format"] += 1
            logging.getLogger("active_sync.api").info(
                "CHECK_ROW id=%s discard=format", row.report_id or ""
            )
            continue
        if _normalized(row.user) != _normalized(user):
            discarded["user"] += 1
            logging.getLogger("active_sync.api").info(
                "CHECK_ROW id=%s discard=user", row.report_id or ""
            )
            continue
        delta = (row.requested_at - trigger_naive).total_seconds()
        if delta < -tolerance_seconds:
            discarded["time"] += 1
            logging.getLogger("active_sync.api").info(
                "TIME_FILTER trigger_local=%s trigger_naive=%s requested_at=%s "
                "delta_seconds=%s tolerance_seconds=%s",
                trigger_local.isoformat(),
                trigger_naive.isoformat(),
                row.requested_at.isoformat(),
                delta,
                -tolerance_seconds,
            )
            logging.getLogger("active_sync.api").info(
                "CHECK_ROW id=%s discard=time", row.report_id or ""
            )
            continue
        candidates.append((abs(delta), row))

    if not candidates:
        logging.getLogger("active_sync.api").info(
            "GRID_SUMMARY rows_total=%s rows_parsed=%s discard_name=%s discard_user=%s "
            "discard_format=%s discard_status=%s discard_requested_at=%s "
            "discard_time=%s selected=%s",
            len(rows),
            len(rows),
            discarded["name"],
            discarded["user"],
            discarded["format"],
            discarded["status"],
            discarded["requested_at"],
            discarded["time"],
            False,
        )
        return None
    candidates.sort(key=lambda item: item[0])
    if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) <= 1:
        logging.getLogger("active_sync.api").info(
            "GRID_SUMMARY rows_total=%s rows_parsed=%s discard_name=%s discard_user=%s "
            "discard_format=%s discard_status=%s discard_requested_at=%s "
            "discard_time=%s selected=%s",
            len(rows),
            len(rows),
            discarded["name"],
            discarded["user"],
            discarded["format"],
            discarded["status"],
            discarded["requested_at"],
            discarded["time"],
            False,
        )
        summary = "; ".join(
            f"ID={row.report_id or '?'} nome={row.name} data={row.requested_at}"
            for _, row in candidates[:5]
        )
        raise ReportAmbiguityError(
            "Foram encontrados múltiplos relatórios compatíveis com esta execução: " + summary
        )
    selected = candidates[0][1]
    selected_delta = (selected.requested_at - trigger_naive).total_seconds()
    logging.getLogger("active_sync.api").info(
        "SELECTED_REPORT id=%s file=%s delta_seconds=%s",
        selected.report_id or "",
        selected.name,
        selected_delta,
    )
    logging.getLogger("active_sync.api").info(
        "GRID_SUMMARY rows_total=%s rows_parsed=%s discard_name=%s discard_user=%s "
        "discard_format=%s discard_status=%s discard_requested_at=%s "
        "discard_time=%s selected=%s",
        len(rows),
        len(rows),
        discarded["name"],
        discarded["user"],
        discarded["format"],
        discarded["status"],
        discarded["requested_at"],
        discarded["time"],
        selected.report_id or selected.name,
    )
    return selected


def _fetch_grid(client: ActiveClient) -> list[ReportRow]:
    try:
        response = client.session.post(
            client.url("/SITE/Relatorio/Grid_RelatoriosAssincronos"),
            params={"formularioID": client.settings.formulario_id, "view": "null"},
            timeout=client.settings.http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise ReportRequestError(f"Não foi possível consultar a grade de relatórios: {exc}") from exc
    if response.status_code != 200:
        raise ReportRequestError(f"A grade de relatórios retornou HTTP {response.status_code}.")
    text = response.text
    lowered = text.casefold()
    if "name=\"password\"" in lowered and "/site/login/loging" in lowered:
        raise ReportRequestError("A sessão retornou para a tela de login durante o polling.")
    rows = parse_report_grid(text, client.settings.base_url)
    logging.getLogger("active_sync.api").info(
        "GRID_FETCH status=%s content_type=%s url=%s html_size=%s tr_count=%s rows=%s",
        response.status_code,
        response.headers.get("Content-Type", ""),
        response.url,
        len(text),
        len(BeautifulSoup(text, "html.parser").select("tr")),
        len(rows),
    )
    return rows


def _wait_for_row(
    client: ActiveClient,
    logger: logging.Logger,
    selector,
) -> ReportRow:
    deadline = time.monotonic() + client.settings.report_timeout_seconds
    last_candidates: list[ReportRow] = []
    while True:
        rows = _fetch_grid(client)
        selected = selector(rows)
        if selected is not None:
            last_candidates = [selected]
            if selected.status == "erro":
                raise ReportRequestError(
                    f"O relatório {selected.report_id or selected.name} foi marcado pelo Active "
                    "com erro de processamento. Não repita automaticamente a solicitação."
                )
            if selected.status == "cancelado":
                raise ReportRequestError(
                    f"O relatório {selected.report_id or selected.name} foi cancelado no Active."
                )
            if selected.status == "concluído" and selected.download_url:
                logger.info("Relatório localizado: ID %s", selected.report_id or "não informado")
                logger.info("Link de download disponível (URL ocultada)")
                return selected
            logger.info(
                "Relatório %s ainda está processando", selected.report_id or selected.name
            )
        else:
            logger.info("Relatório ainda não apareceu na grade")

        if time.monotonic() >= deadline:
            summary = "; ".join(
                f"ID={row.report_id or '?'} nome={row.name} status={row.status}"
                for row in last_candidates
            ) or "nenhum candidato"
            raise ReportTimeoutError(
                "O relatório não ficou disponível dentro do tempo limite. Últimos candidatos: "
                + summary
            )
        time.sleep(client.settings.poll_interval_seconds)


def poll_current_report(
    client: ActiveClient,
    trigger_local: datetime,
    logger: logging.Logger,
) -> ReportRow:
    return _wait_for_row(
        client,
        logger,
        lambda rows: select_current_report(
            rows,
            report_name=client.settings.report_name,
            report_format=client.settings.report_format,
            user=client.settings.user,
            trigger_local=trigger_local,
            tolerance_seconds=client.settings.report_time_tolerance_seconds,
        ),
    )


def poll_report_by_id(
    client: ActiveClient,
    report_id: str,
    logger: logging.Logger,
) -> ReportRow:
    clean_id = report_id.strip()
    if not clean_id:
        raise ReportRequestError("O ID do relatório não pode ser vazio.")
    return _wait_for_row(
        client,
        logger,
        lambda rows: next((row for row in rows if row.report_id == clean_id), None),
    )
