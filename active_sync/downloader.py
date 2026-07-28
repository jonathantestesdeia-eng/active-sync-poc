"""Download streaming e validação segura do ZIP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import unquote, urlparse
import zipfile

import requests

from .client import ActiveClient
from .exceptions import DownloadError, InvalidZipError


WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: Path
    size_bytes: int
    duration_seconds: float


def sanitize_windows_filename(name: str, default: str = "relatorio.zip") -> str:
    candidate = unquote(name).replace("\\", "_").replace("/", "_")
    candidate = re.sub(r'[<>:"|?*\x00-\x1f]', "_", candidate).strip().rstrip(". ")
    candidate = candidate.lstrip(". ")
    if not candidate:
        candidate = default
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    if stem.upper() in WINDOWS_RESERVED:
        stem = f"_{stem}"
    candidate = f"{stem}{suffix}"
    if len(candidate) > 180:
        candidate = f"{stem[:160]}{suffix}"
    if not candidate.casefold().endswith(".zip"):
        candidate = f"{candidate}.zip"
    return candidate


def _filename_from_url(url: str) -> str:
    path_name = Path(unquote(urlparse(url).path)).name
    return sanitize_windows_filename(path_name or "relatorio.zip")


def _available_path(directory: Path, filename: str) -> Path:
    desired = directory / filename
    if not desired.exists():
        return desired
    stem = desired.stem
    suffix = desired.suffix
    for number in range(1, 10_000):
        candidate = directory / f"{stem}-{number}{suffix}"
        if not candidate.exists():
            return candidate
    raise DownloadError("Não foi possível criar um nome de arquivo ZIP exclusivo.")


def _validate_zip(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            signature = handle.read(4)
    except OSError as exc:
        raise DownloadError(f"Não foi possível ler o arquivo temporário: {exc}") from exc
    if signature not in ZIP_SIGNATURES or not zipfile.is_zipfile(path):
        raise InvalidZipError("O arquivo baixado não é um ZIP válido.")


def download_zip(
    client: ActiveClient,
    download_url: str,
    downloads_dir: Path,
    logger,
    *,
    keep_files: bool = False,
) -> DownloadResult:
    if not download_url:
        raise DownloadError("O relatório não possui URL de download.")
    parsed_url = urlparse(download_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise DownloadError("A URL de download não é HTTP/HTTPS válida.")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    final_path = _available_path(downloads_dir, _filename_from_url(download_url))
    temporary_path: Path | None = None
    started = time.monotonic()
    received = 0
    logger.info("Iniciando download do ZIP (URL ocultada)")
    try:
        try:
            response = client.session.get(
                download_url,
                stream=True,
                allow_redirects=True,
                timeout=client.settings.http_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DownloadError(f"Não foi possível baixar o ZIP: {exc}") from exc
        if response.status_code != 200:
            raise DownloadError(f"O download retornou HTTP {response.status_code}.")

        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".active-sync-",
            suffix=".part",
            dir=downloads_dir,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            try:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        temporary.write(chunk)
                        received += len(chunk)
            except requests.RequestException as exc:
                raise DownloadError(f"O download foi interrompido: {exc}") from exc

        if received <= 0:
            raise DownloadError("O download retornou um arquivo vazio.")
        _validate_zip(temporary_path)
        temporary_path.replace(final_path)
        temporary_path = None
    except Exception:
        if temporary_path is not None and temporary_path.exists() and not keep_files:
            temporary_path.unlink()
        elif temporary_path is not None and temporary_path.exists():
            logger.warning("Arquivo temporário preservado para diagnóstico: %s", temporary_path)
        raise

    duration = time.monotonic() - started
    logger.info("Download concluído: %s bytes em %.2f segundos", received, duration)
    logger.info("ZIP salvo em: %s", final_path)
    return DownloadResult(path=final_path, size_bytes=received, duration_seconds=duration)
