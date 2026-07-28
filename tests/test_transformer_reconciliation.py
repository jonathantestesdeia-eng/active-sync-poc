from __future__ import annotations

from pathlib import Path

import pandas as pd

from active_sync.transformer.reconciliation import (
    apply_reconciliation_rules,
    infer_reconciliation_rules,
    reconcile_datasets,
    write_reconciliation_markdown,
)


def raw_frame() -> pd.DataFrame:
    common = {
        "Transportador": "Transportadora X",
        "Cancelamento": None,
        "Emissão": "21/07/2026",
        "Entrega": None,
        "Valor Frete": 10,
        "Operação Fiscal": None,
        "Redespacho": None,
        "Observacao": None,
    }
    rows = [
        {
            **common,
            "Nota Fiscal": "001",
            "CTe": "101",
            "Tipo": "TIPO MANTIDO",
            "Saída": "21/07/2026",
            "Destinatário": "200 - CLIENTE",
            "Tomador": "100 - EMPRESA",
            "Fatura": None,
            "Aprovação Financeira": None,
        },
        {
            **common,
            "Nota Fiscal": "002",
            "CTe": "102",
            "Tipo": "DEVOLUCAO",
            "Saída": "21/07/2026",
            "Destinatário": "200 - CLIENTE",
            "Tomador": "100 - EMPRESA",
            "Fatura": None,
            "Aprovação Financeira": None,
        },
        {
            **common,
            "Nota Fiscal": "003",
            "CTe": "103",
            "Tipo": "TIPO MANTIDO",
            "Saída": None,
            "Destinatário": "200 - CLIENTE",
            "Tomador": "100 - EMPRESA",
            "Fatura": None,
            "Aprovação Financeira": None,
        },
        {
            **common,
            "Nota Fiscal": "004",
            "CTe": "104",
            "Tipo": "TIPO MANTIDO",
            "Saída": "21/07/2026",
            "Destinatário": "100 - EMPRESA",
            "Tomador": "100 - EMPRESA",
            "Fatura": None,
            "Aprovação Financeira": None,
        },
        {
            **common,
            "Nota Fiscal": "005",
            "CTe": "105",
            "Tipo": "TIPO MANTIDO",
            "Saída": "21/07/2026",
            "Destinatário": "200 - CLIENTE",
            "Tomador": "100 - EMPRESA",
            "Fatura": "500",
            "Aprovação Financeira": None,
        },
    ]
    return pd.DataFrame(rows)


def reference_frame() -> pd.DataFrame:
    return pd.DataFrame({"Nota Fiscal": ["001"], "Tipo CTe": ["TIPO MANTIDO"]})


def test_infers_rules_from_reference_without_fixed_document_type() -> None:
    rules = infer_reconciliation_rules(raw_frame(), reference_frame())

    assert rules.allowed_document_types == frozenset({"tipo mantido"})
    assert rules.require_departure
    assert rules.exclude_recipient_equal_payer
    assert rules.require_financial_approval_for_invoiced


def test_applies_inferred_rules_and_reconciles_exact_set() -> None:
    raw = raw_frame()
    reference = reference_frame()
    rules = infer_reconciliation_rules(raw, reference)

    filtered = apply_reconciliation_rules(raw, rules)
    reconciled, result = reconcile_datasets(raw, reference, rules)

    assert filtered["Nota Fiscal"].tolist() == ["001"]
    assert reconciled["Nota Fiscal"].tolist() == ["001"]
    assert result.is_reconciled
    assert result.original_python_count == 5
    assert result.reconciled_python_count == 1
    assert not result.remaining_only_python
    assert not result.remaining_only_powerquery
    assert all(entry.present_in_active for entry in result.only_python)
    assert all(not entry.created_by_rule for entry in result.only_python)
    assert all(entry.possible_reasons for entry in result.only_python)


def test_reports_notes_present_only_in_powerquery() -> None:
    rules = infer_reconciliation_rules(raw_frame(), reference_frame())
    reference = pd.DataFrame(
        {"Nota Fiscal": ["001", "999"], "Tipo CTe": ["TIPO MANTIDO", "TIPO MANTIDO"]}
    )

    _, result = reconcile_datasets(raw_frame(), reference, rules)

    assert result.only_powerquery == ("999",)
    assert not result.is_reconciled


def test_detects_duplicate_notes_and_ctes() -> None:
    raw = pd.concat([raw_frame(), raw_frame().iloc[[0]]], ignore_index=True)

    _, result = reconcile_datasets(raw, reference_frame())

    assert result.duplicate_notes_python[0].value == "001"
    assert result.duplicate_notes_python[0].count == 2
    assert result.duplicate_ctes_python[0].value == "101"


def test_writes_reconciliation_markdown(tmp_path: Path) -> None:
    _, result = reconcile_datasets(raw_frame(), reference_frame())

    output = write_reconciliation_markdown(result, tmp_path / "RECONCILIACAO.md")
    text = output.read_text(encoding="utf-8")

    assert "Critério de aceitação: **ATENDIDO**" in text
    assert "Lista completa dos registros originalmente excedentes" in text
    assert "Fatura preenchida sem aprovação financeira" in text
