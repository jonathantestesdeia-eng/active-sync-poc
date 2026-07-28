from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from openpyxl import Workbook

from active_sync.excel_reader import inspect_excel


def test_reads_xlsx_as_text_and_masks_sensitive_preview(tmp_path: Path) -> None:
    path = tmp_path / "relatorio.xlsx"
    workbook = Workbook()
    empty = workbook.active
    empty.title = "Vazia"
    data = workbook.create_sheet("Dados")
    data.append(["CNPJ", "Chave de Acesso", "Pedido", "Valor"])
    data.append(["00123456000199", "12345678901234567890", "0000123", 10])
    workbook.save(path)

    result = inspect_excel(path, Mock())

    assert result.sheet_names == ("Vazia", "Dados")
    assert result.selected_sheet == "Dados"
    assert result.row_count == 1
    assert result.columns == ("CNPJ", "Chave de Acesso", "Pedido", "Valor")
    assert result.masked_preview[0]["CNPJ"] == "***0199"
    assert result.masked_preview[0]["Chave de Acesso"] == "***7890"
    assert result.masked_preview[0]["Pedido"] == "***0123"
