from __future__ import annotations

from pathlib import Path

import pandas as pd

from active_sync.transformer.comparator import (
    compare_dataframes,
    write_comparison_report,
)


def test_comparator_normalizes_nulls_text_dates_numbers_and_identifiers() -> None:
    python = pd.DataFrame(
        {
            "CNPJ": ["00123", None],
            "Destinatário": ["  CLIENTE   TESTE ", ""],
            "Valor Frete": [1234.56, None],
            "Saída": [pd.Timestamp("2026-07-21"), pd.NaT],
        }
    )
    powerquery = pd.DataFrame(
        {
            "CNPJ": ["00123", "  "],
            "Destinatário": ["cliente teste", pd.NA],
            "Valor Frete": ["1.234,56", ""],
            "Saída": ["21/07/2026", None],
        }
    )

    report = compare_dataframes(python, powerquery)

    assert report.is_fully_equivalent
    assert report.overall_equivalence_percent == 100.0
    assert not report.divergences


def test_comparator_preserves_identifier_leading_zeros() -> None:
    python = pd.DataFrame({"CNPJ": ["00123"]})
    powerquery = pd.DataFrame({"CNPJ": [123]})

    report = compare_dataframes(python, powerquery)

    result = report.result_for("CNPJ")
    assert result.equal_records == 0
    assert result.different_records == 1
    assert result.equivalence_percent == 0.0


def test_comparator_does_not_treat_invalid_typed_value_as_null() -> None:
    python = pd.DataFrame({"Valor Frete": ["inválido"], "Saída": ["sem data"]})
    powerquery = pd.DataFrame({"Valor Frete": [None], "Saída": [None]})

    report = compare_dataframes(python, powerquery)

    assert report.result_for("Valor Frete").different_records == 1
    assert report.result_for("Saída").different_records == 1


def test_comparator_reports_cell_divergence_and_column_percentage() -> None:
    python = pd.DataFrame({"Prazo": [3, 3]})
    powerquery = pd.DataFrame({"Prazo": [3, 4]})

    report = compare_dataframes(python, powerquery)

    result = report.result_for("Prazo")
    assert result.equal_records == 1
    assert result.different_records == 1
    assert result.equivalence_percent == 50.0
    assert report.divergences[0].row_number == 2
    assert report.divergences[0].column == "Prazo"
    assert report.divergences[0].python_value == 3
    assert report.divergences[0].powerquery_value == 4


def test_comparator_reports_structural_differences_without_hiding_values() -> None:
    python = pd.DataFrame({"A": ["x", "y"], "B": [1, 2]})
    powerquery = pd.DataFrame({"B": [1], "C": ["z"]})

    report = compare_dataframes(python, powerquery)

    assert not report.is_structurally_equivalent
    assert not report.column_order_matches
    assert any("Quantidade de linhas" in error for error in report.structural_errors)
    assert any("ausentes no Python" in error for error in report.structural_errors)
    assert report.result_for("A").different_records == 2
    assert report.result_for("C").different_records == 2


def test_comparator_can_align_rows_by_explicit_key() -> None:
    python = pd.DataFrame(
        {"Nota Fiscal": ["002", "001", "003"], "Cidade Origem": ["B", "A", "C"]}
    )
    powerquery = pd.DataFrame(
        {"Nota Fiscal": ["001", "002"], "Cidade Origem": ["A", "B"]}
    )

    report = compare_dataframes(python, powerquery, key_columns=["Nota Fiscal"])

    assert report.alignment_keys == ("Nota Fiscal",)
    assert report.matched_row_count == 2
    assert report.result_for("Cidade Origem").equal_records == 2
    assert report.result_for("Cidade Origem").different_records == 1
    assert report.result_for("Cidade Origem").equivalence_percent == 66.67


def test_comparator_reports_populated_reference_coverage() -> None:
    python = pd.DataFrame({"Prazo": [None, None]})
    powerquery = pd.DataFrame({"Prazo": [None, None]})

    result = compare_dataframes(python, powerquery).result_for("Prazo")

    assert result.equivalence_percent == 100.0
    assert result.python_populated_records == 0
    assert result.powerquery_populated_records == 0


def test_comparator_uses_observed_reference_type_for_derived_columns() -> None:
    python = pd.DataFrame({"Prazo": [" entregue no prazo "], "Data": ["JULHO"]})
    powerquery = pd.DataFrame({"Prazo": ["Entregue no prazo"], "Data": ["julho"]})

    report = compare_dataframes(python, powerquery)

    assert report.result_for("Prazo").equivalence_percent == 100.0
    assert report.result_for("Data").equivalence_percent == 100.0


def test_comparator_detects_duplicate_columns() -> None:
    python = pd.DataFrame([[1, 2]], columns=["CNPJ", "CNPJ"])
    powerquery = pd.DataFrame({"CNPJ": [1]})

    report = compare_dataframes(python, powerquery)

    assert any("duplicadas no Python" in error for error in report.structural_errors)
    assert report.result_for("CNPJ").different_records == 1


def test_writes_complete_text_report(tmp_path: Path) -> None:
    report = compare_dataframes(
        pd.DataFrame({"Situação": [None]}),
        pd.DataFrame({"Situação": ["ATRASADO"]}),
    )

    output = write_comparison_report(report, tmp_path / "equivalencia.txt")
    text = output.read_text(encoding="utf-8")

    assert "Equivalência geral dos valores" in text
    assert "Linha 1" in text
    assert "Coluna: Situação" in text
    assert "Power Query: 'ATRASADO'" in text
