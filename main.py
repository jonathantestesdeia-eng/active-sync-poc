"""Ponto de entrada da prova de conceito completa do Active Sync."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from active_sync.auth import list_available_contexts, login, select_company_context
from active_sync.client import ActiveClient
from active_sync.config import Settings
from active_sync.exceptions import ActiveSyncError
from active_sync.downloader import download_zip
from active_sync.excel_reader import inspect_excel
from active_sync.extractor import extract_zip
from active_sync.logger import configure_logging
from active_sync.report_grid import poll_current_report, poll_report_by_id
from active_sync.reports import confirm_report_request, request_report, resolve_report_window


PROJECT_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Active Sync POC — fluxo local completo")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--login-only",
        action="store_true",
        help="Faz login, seleciona o contexto e valida a sessão operacional.",
    )
    mode.add_argument(
        "--discover-contexts",
        action="store_true",
        help="Lista valores de empresa, filial e acesso sem selecionar o contexto.",
    )
    mode.add_argument(
        "--poll-report-id",
        metavar="ID",
        help="Acompanha um relatório já criado sem solicitar outro.",
    )
    parser.add_argument(
        "--company-id",
        help="Valor de empresa retornado pela descoberta, usado para consultar filiais.",
    )
    parser.add_argument("--date-from", help="Data inicial no formato DD/MM/AAAA.")
    parser.add_argument("--date-to", help="Data final no formato DD/MM/AAAA.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma o disparo do relatório sem perguntar no terminal.",
    )
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Preserva arquivos temporários úteis quando ocorrer uma falha.",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    logger = configure_logging(PROJECT_ROOT)
    started = time.monotonic()
    logger.info("Iniciando Active Sync POC")

    try:
        logger.info("Validando configurações")
        settings = Settings.from_env()
        with ActiveClient(settings) as client:
            login_result = login(client, logger)
            if args.discover_contexts:
                list_available_contexts(client, login_result, logger, args.company_id)
                logger.info("Descoberta concluída; nenhum contexto foi selecionado")
            else:
                settings.validate_context()
                select_company_context(client, login_result, logger)
                if args.poll_report_id:
                    logger.info("Acompanhando relatório existente: ID %s", args.poll_report_id)
                    report_row = poll_report_by_id(client, args.poll_report_id, logger)
                    download_result = download_zip(
                        client,
                        report_row.download_url or "",
                        PROJECT_ROOT / "downloads",
                        logger,
                        keep_files=args.keep_files,
                    )
                    extraction = extract_zip(
                        download_result.path,
                        PROJECT_ROOT / "extraidos",
                        logger,
                        keep_files=args.keep_files,
                    )
                    inspect_excel(extraction.excel_path, logger)
                    logger.info(
                        "Prova de conceito concluída em %.2f segundos",
                        time.monotonic() - started,
                    )
                    logger.info("Nenhum novo relatório foi solicitado")
                elif args.login_only:
                    logger.info("Etapa 2 concluída em %.2f segundos", time.monotonic() - started)
                    logger.info("Nenhum relatório foi solicitado")
                else:
                    window = resolve_report_window(
                        args.date_from,
                        args.date_to,
                        settings.date_from,
                        settings.date_to,
                    )
                    logger.info(
                        "Intervalo preparado: %s até %s",
                        window.formatted_from,
                        window.formatted_to,
                    )
                    if not confirm_report_request(window, args.yes):
                        logger.info("Solicitação cancelada pelo usuário; nenhum relatório foi criado")
                        return 0
                    request_result = request_report(client, window, logger)
                    if not request_result.accepted:
                        logger.warning(
                            "Resposta de erro recebida; verificando a grade para evitar duplicidade"
                        )
                    report_row = poll_current_report(client, request_result.local_before, logger)
                    download_result = download_zip(
                        client,
                        report_row.download_url or "",
                        PROJECT_ROOT / "downloads",
                        logger,
                        keep_files=args.keep_files,
                    )
                    extraction = extract_zip(
                        download_result.path,
                        PROJECT_ROOT / "extraidos",
                        logger,
                        keep_files=args.keep_files,
                    )
                    inspect_excel(extraction.excel_path, logger)
                    logger.info(
                        "Prova de conceito concluída em %.2f segundos",
                        time.monotonic() - started,
                    )
        return 0
    except ActiveSyncError as exc:
        logger.error("Falha: %s", exc)
        logger.info("Execução encerrada em %.2f segundos", time.monotonic() - started)
        return 1
    except KeyboardInterrupt:
        logger.warning("Execução cancelada pelo usuário")
        return 130


if __name__ == "__main__":
    sys.exit(run())
