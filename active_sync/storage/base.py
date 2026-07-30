"""Contrato independente para armazenamento permanente de arquivos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from active_sync.exceptions import StorageDisabledError


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Metadados mínimos retornados por qualquer provedor de armazenamento."""

    provider: str
    file_id: str
    name: str
    web_url: str | None = None


class FileStorage(Protocol):
    """Porta de saída para persistência externa de um arquivo local."""

    provider: str

    def ensure_directory(self, path: tuple[str, ...]) -> str: ...

    def store_file(
        self,
        source: Path,
        *,
        object_name: str | None = None,
        content_type: str | None = None,
        directory_id: str | None = None,
    ) -> StoredFile: ...


class DisabledFileStorage:
    """Implementação segura usada enquanto o armazenamento está desabilitado."""

    provider = "disabled"

    def ensure_directory(self, path: tuple[str, ...]) -> str:
        del path
        raise StorageDisabledError("O armazenamento externo está desabilitado.")

    def store_file(
        self,
        source: Path,
        *,
        object_name: str | None = None,
        content_type: str | None = None,
        directory_id: str | None = None,
    ) -> StoredFile:
        del source, object_name, content_type, directory_id
        raise StorageDisabledError("O armazenamento externo está desabilitado.")
