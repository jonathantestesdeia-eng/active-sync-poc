from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock
import zipfile

import pytest

from active_sync.exceptions import ExtractionError
from active_sync.extractor import extract_zip


def make_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def test_extracts_single_excel_safely(tmp_path: Path) -> None:
    zip_path = tmp_path / "relatorio.zip"
    make_zip(zip_path, {"pasta/relatorio.xlsx": b"xlsx-de-teste", "leia-me.txt": b"ok"})

    result = extract_zip(zip_path, tmp_path / "extraidos", Mock())

    assert result.excel_path.name == "relatorio.xlsx"
    assert len(result.extracted_files) == 2


def test_rejects_path_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "malicioso.zip"
    make_zip(zip_path, {"../fora.xlsx": b"perigoso"})

    with pytest.raises(ExtractionError, match="path traversal"):
        extract_zip(zip_path, tmp_path / "extraidos", Mock())

    assert not (tmp_path / "fora.xlsx").exists()


def test_rejects_multiple_excel_files(tmp_path: Path) -> None:
    zip_path = tmp_path / "multiplos.zip"
    make_zip(zip_path, {"a.xlsx": b"a", "b.xlsx": b"b"})

    with pytest.raises(ExtractionError, match="mais de um"):
        extract_zip(zip_path, tmp_path / "extraidos", Mock())
