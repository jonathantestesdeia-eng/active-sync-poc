"""Extração segura do ZIP e localização do Excel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile

from .exceptions import ExtractionError


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    directory: Path
    extracted_files: tuple[Path, ...]
    excel_path: Path


def _safe_member_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    if "\x00" in normalized:
        raise ExtractionError("O ZIP contém um nome de arquivo inválido.")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ExtractionError(f"O ZIP contém um caminho absoluto inseguro: {name}")
    path = PurePosixPath(normalized)
    if any(part == ".." for part in path.parts):
        raise ExtractionError(f"O ZIP contém tentativa de path traversal: {name}")
    if not path.parts or all(part in {"", "."} for part in path.parts):
        raise ExtractionError("O ZIP contém uma entrada sem nome válido.")
    return path


def _exclusive_directory(root: Path) -> Path:
    base = root / datetime.now().strftime("%Y%m%d_%H%M%S")
    if not base.exists():
        return base
    for number in range(1, 10_000):
        candidate = root / f"{base.name}-{number}"
        if not candidate.exists():
            return candidate
    raise ExtractionError("Não foi possível criar uma pasta exclusiva para a extração.")


def _is_symlink(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    return stat.S_ISLNK(mode)


def _choose_excel(files: list[Path]) -> Path:
    excel_files = [
        path
        for path in files
        if path.suffix.casefold() in {".xlsx", ".xls"} and not path.name.startswith("~$")
    ]
    if not excel_files:
        raise ExtractionError("O ZIP não contém um arquivo Excel compatível.")
    if len(excel_files) > 1:
        names = "; ".join(str(path) for path in excel_files)
        raise ExtractionError(
            "O ZIP contém mais de um arquivo Excel e não há regra segura para escolher: " + names
        )
    return excel_files[0]


def extract_zip(
    zip_path: Path,
    extraction_root: Path,
    logger,
    *,
    keep_files: bool = False,
) -> ExtractionResult:
    if not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
        raise ExtractionError("O arquivo informado para extração não é um ZIP válido.")
    extraction_root.mkdir(parents=True, exist_ok=True)
    destination = _exclusive_directory(extraction_root)
    destination.mkdir(parents=False, exist_ok=False)
    extracted: list[Path] = []
    logger.info("Extraindo ZIP em: %s", destination)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = archive.infolist()
            safe_members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for member in members:
                safe_path = _safe_member_path(member.filename)
                if _is_symlink(member):
                    raise ExtractionError(
                        f"O ZIP contém um link simbólico não permitido: {member.filename}"
                    )
                safe_members.append((member, safe_path))

            root_resolved = destination.resolve()
            for member, relative in safe_members:
                target = destination.joinpath(*relative.parts)
                target_resolved = target.resolve()
                if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
                    raise ExtractionError(
                        f"A entrada sairia da pasta de extração: {member.filename}"
                    )
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ExtractionError(f"O ZIP contém entradas duplicadas: {member.filename}")
                with archive.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                extracted.append(target)

        excel_path = _choose_excel(extracted)
    except Exception:
        if keep_files:
            logger.warning("Extração parcial preservada para diagnóstico: %s", destination)
        else:
            shutil.rmtree(destination, ignore_errors=True)
        raise

    logger.info("Arquivos extraídos: %d", len(extracted))
    for path in extracted:
        logger.info("  %s", path)
    logger.info("Excel localizado: %s", excel_path)
    return ExtractionResult(
        directory=destination,
        extracted_files=tuple(extracted),
        excel_path=excel_path,
    )
