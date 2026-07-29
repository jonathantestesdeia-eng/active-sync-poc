from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from active_sync.exceptions import ReportAmbiguityError
from active_sync.report_grid import ReportRow, parse_report_grid, select_current_report


FIXTURES = Path(__file__).parent / "fixtures"


def test_parser_reads_completed_processing_cancelled_and_error_rows() -> None:
    rows = parse_report_grid((FIXTURES / "grid_reports.html").read_text(encoding="utf-8"))

    assert rows[0].report_id == "101"
    assert rows[0].status == "concluído"
    assert rows[0].download_url == "https://arquivos.example.invalid/relatorio.zip"
    assert rows[1].status == "processando"
    assert rows[1].download_url is None
    assert rows[2].status == "cancelado"
    assert rows[3].status == "erro"


def test_time_filter_selects_current_user_report() -> None:
    rows = parse_report_grid((FIXTURES / "grid_reports.html").read_text(encoding="utf-8"))

    selected = select_current_report(
        rows,
        report_name="Conhecimento - CTe",
        report_format="Excel__NotaFiscal",
        user=" USUARIO@EXEMPLO.INVALID ",
        trigger_local=datetime(2026, 7, 21, 11, 50, 15),
        tolerance_seconds=120,
    )

    assert selected is not None
    assert selected.report_id == "101"


def test_old_report_is_not_selected() -> None:
    rows = parse_report_grid((FIXTURES / "grid_reports.html").read_text(encoding="utf-8"))

    selected = select_current_report(
        rows,
        report_name="Conhecimento - CTe",
        report_format="Excel__NotaFiscal",
        user="usuario@exemplo.invalid",
        trigger_local=datetime(2026, 7, 21, 12, 0, 0),
        tolerance_seconds=120,
    )

    assert selected is None


def test_utc_trigger_is_compared_in_active_sao_paulo_timezone() -> None:
    row = ReportRow(
        "200",
        "Conhecimento - CTe_29072026_154805",
        "Excel__NotaFiscal",
        "usuario@exemplo.invalid",
        datetime(2026, 7, 29, 15, 48, 5),
        None,
        "processando",
    )

    selected = select_current_report(
        [row],
        report_name="Conhecimento - CTe",
        report_format="Excel__NotaFiscal",
        user="usuario@exemplo.invalid",
        trigger_local=datetime(
            2026, 7, 29, 18, 48, 4, 733309, tzinfo=timezone.utc
        ),
        tolerance_seconds=120,
    )

    assert selected is row


def test_report_created_one_second_after_utc_trigger_is_selected() -> None:
    row = ReportRow(
        "201",
        "Conhecimento - CTe_29072026_154805",
        "Excel__NotaFiscal",
        "usuario@exemplo.invalid",
        datetime(2026, 7, 29, 15, 48, 5),
        None,
        "processando",
    )

    selected = select_current_report(
        [row],
        report_name="Conhecimento - CTe",
        report_format="Excel__NotaFiscal",
        user="usuario@exemplo.invalid",
        trigger_local=datetime(2026, 7, 29, 18, 48, 4, tzinfo=timezone.utc),
        tolerance_seconds=120,
    )

    assert selected is row


def test_report_older_than_tolerance_is_rejected_after_timezone_conversion() -> None:
    row = ReportRow(
        "202",
        "Conhecimento - CTe_29072026_154603",
        "Excel__NotaFiscal",
        "usuario@exemplo.invalid",
        datetime(2026, 7, 29, 15, 46, 3),
        None,
        "processando",
    )

    selected = select_current_report(
        [row],
        report_name="Conhecimento - CTe",
        report_format="Excel__NotaFiscal",
        user="usuario@exemplo.invalid",
        trigger_local=datetime(2026, 7, 29, 18, 48, 4, tzinfo=timezone.utc),
        tolerance_seconds=120,
    )

    assert selected is None


def test_naive_trigger_is_treated_as_active_local_time() -> None:
    row = ReportRow(
        "203",
        "Conhecimento - CTe_29072026_154805",
        "Excel__NotaFiscal",
        "usuario@exemplo.invalid",
        datetime(2026, 7, 29, 15, 48, 5),
        None,
        "processando",
    )

    selected = select_current_report(
        [row],
        report_name="Conhecimento - CTe",
        report_format="Excel__NotaFiscal",
        user="usuario@exemplo.invalid",
        trigger_local=datetime(2026, 7, 29, 15, 48, 4),
        tolerance_seconds=120,
    )

    assert selected is row


def test_equally_plausible_candidates_raise_ambiguity() -> None:
    when = datetime(2026, 7, 21, 11, 50, 12)
    rows = [
        ReportRow("1", "Conhecimento - CTe_a", "Excel__NotaFiscal", "u", when, None, "processando"),
        ReportRow("2", "Conhecimento - CTe_b", "Excel__NotaFiscal", "u", when, None, "processando"),
    ]

    with pytest.raises(ReportAmbiguityError, match="múltiplos"):
        select_current_report(
            rows,
            report_name="Conhecimento - CTe",
            report_format="Excel__NotaFiscal",
            user="u",
            trigger_local=when,
            tolerance_seconds=120,
        )
