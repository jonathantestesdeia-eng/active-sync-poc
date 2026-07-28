"""Leitura somente texto do Excel extraido."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata

import pandas as pd

from .exceptions import ExcelReadError


SENSITIVE_HEADER = re.compile(
    r"(?:\bcte\b|pre-?cte|cpf|cnpj|\bie\b|inscricao|e-?mail|telefone|"
    r"celular|chave|protocolo|nota fiscal|pedido|transportador|remetente|"
    r"destinatario|tomador|consignatario|redespacho|usuario|nome|"
    r"razao.*social|endereco|logradouro|complemento|placa|observacao|"
    r"apolice|seguradora|contrato)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ExcelInspectionResult:
    path: Path
    size_bytes: int
    sheet_names: tuple[str, ...]
    selected_sheet: str
    row_count: int
    column_count: int
    columns: tuple[str, ...]
    masked_preview: tuple[dict[str, str], ...]


def _mask(value: object) -> str:
    text = "" if value is None else str(value)
    if not text:
        return text
    visible = text[-4:] if len(text) > 4 else text[-1:]
    return f"***{visible}"


def _masked_records(frame: pd.DataFrame) -> tuple[dict[str, str], ...]:
    records: list[dict[str, str]] = []
    for raw_record in frame.head(5).to_dict(orient="records"):
        record: dict[str, str] = {}
        for column, value in raw_record.items():
            column_name = str(column)
            normalized_column = "".join(
                character
                for character in unicodedata.normalize("NFD", column_name)
                if unicodedata.category(character) != "Mn"
            )
            text = "" if pd.isna(value) else str(value)
            value_looks_sensitive = "@" in text or bool(re.search(r"\d{11,}", text))
            record[column_name] = (
                _mask(text)
                if SENSITIVE_HEADER.search(normalized_column) or value_looks_sensitive
                else text
            )
        records.append(record)
    return tuple(records)


def read_excel_dataframe(path: Path) -> tuple[pd.DataFrame, tuple[str, ...], str]:
    """Le a primeira planilha nao vazia preservando valores brutos como texto."""
    if path.suffix.casefold() == ".xls":
        raise ExcelReadError("O formato .xls nao e suportado.")
    if path.suffix.casefold() != ".xlsx":
        raise ExcelReadError(f"Formato de Excel nao suportado: {path.suffix}")
    try:
        workbook = pd.ExcelFile(path, engine="openpyxl")
        sheet_names = tuple(workbook.sheet_names)
        if not sheet_names:
            raise ExcelReadError("O arquivo Excel nao contem planilhas.")
        selected_sheet = sheet_names[0]
        selected_frame: pd.DataFrame | None = None
        for sheet_name in sheet_names:
            frame = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                dtype=str,
                keep_default_na=False,
                engine="openpyxl",
            )
            if selected_frame is None or not frame.empty:
                selected_sheet = sheet_name
                selected_frame = frame
            if not frame.empty:
                break
        if selected_frame is None:
            raise ExcelReadError("Nao foi possivel selecionar uma planilha.")
        return selected_frame, sheet_names, selected_sheet
    except ExcelReadError:
        raise
    except Exception as exc:
        raise ExcelReadError(f"Nao foi possivel ler o arquivo Excel: {exc}") from exc


def inspect_excel(path: Path, logger) -> ExcelInspectionResult:
    """Inspeciona o mesmo DataFrame usado pelo pipeline operacional."""
    selected_frame, sheet_names, selected_sheet = read_excel_dataframe(path)
    columns = tuple(str(column) for column in selected_frame.columns)
    preview = _masked_records(selected_frame)
    size_bytes = path.stat().st_size
    result = ExcelInspectionResult(
        path=path,
        size_bytes=size_bytes,
        sheet_names=sheet_names,
        selected_sheet=selected_sheet,
        row_count=len(selected_frame.index),
        column_count=len(columns),
        columns=columns,
        masked_preview=preview,
    )
    logger.info("Arquivo Excel: %s", path)
    logger.info("Tamanho do Excel: %d bytes", size_bytes)
    logger.info("Planilhas existentes: %s", ", ".join(sheet_names))
    logger.info("Planilha selecionada: %s", selected_sheet)
    logger.info("Registros encontrados: %d", result.row_count)
    logger.info("Quantidade de colunas: %d", result.column_count)
    logger.info("Colunas: %s", list(columns))
    logger.info(
        "Cinco primeiras linhas (dados sensiveis mascarados):\n%s",
        json.dumps(preview, ensure_ascii=False, indent=2),
    )
    return result
