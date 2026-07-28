from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
import zipfile

import pytest
import requests

from active_sync.client import ActiveClient
from active_sync.config import Settings
from active_sync.downloader import download_zip, sanitize_windows_filename
from active_sync.exceptions import InvalidZipError


def settings() -> Settings:
    return Settings(
        base_url="https://exemplo.invalid",
        user="usuario-teste",
        password="segredo-teste",
        user_code=None,
        company_id="empresa-teste",
        branch_id="filial-teste",
        access_type="C",
        is_destinatario=False,
        formulario_id=118,
        report_code="118",
        report_name="Conhecimento - CTe",
        report_format="Excel__NotaFiscal",
        date_from=None,
        date_to=None,
        poll_interval_seconds=10,
        report_timeout_seconds=900,
        http_timeout_seconds=60,
        report_time_tolerance_seconds=120,
    )


def zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("arquivo.txt", "conteúdo de teste")
    return buffer.getvalue()


def client_with_download(content: bytes) -> ActiveClient:
    session = requests.Session()
    response = Mock(status_code=200)
    response.iter_content.return_value = [content[:5], content[5:]]
    session.get = Mock(return_value=response)  # type: ignore[method-assign]
    return ActiveClient(settings(), session=session)


def test_sanitizes_windows_filename() -> None:
    assert sanitize_windows_filename('../CON:<relatório>?*.zip') == '_CON__relatório___.zip'


def test_downloads_and_validates_zip(tmp_path: Path) -> None:
    client = client_with_download(zip_bytes())

    result = download_zip(
        client,
        "https://arquivos.example.invalid/pasta/relatorio.zip",
        tmp_path,
        Mock(),
    )

    assert result.path.name == "relatorio.zip"
    assert result.path.exists()
    assert zipfile.is_zipfile(result.path)


def test_does_not_silently_overwrite_existing_zip(tmp_path: Path) -> None:
    (tmp_path / "relatorio.zip").write_bytes(zip_bytes())
    client = client_with_download(zip_bytes())

    result = download_zip(
        client,
        "https://arquivos.example.invalid/relatorio.zip",
        tmp_path,
        Mock(),
    )

    assert result.path.name == "relatorio-1.zip"


def test_rejects_invalid_zip_and_removes_temporary_file(tmp_path: Path) -> None:
    client = client_with_download("isto não é um zip".encode("utf-8"))

    with pytest.raises(InvalidZipError, match="ZIP válido"):
        download_zip(
            client,
            "https://arquivos.example.invalid/relatorio.zip",
            tmp_path,
            Mock(),
        )

    assert list(tmp_path.iterdir()) == []
