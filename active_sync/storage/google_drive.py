"""Adapter isolado para armazenamento de arquivos no Google Drive."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Callable

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from active_sync.exceptions import StorageConfigurationError, StorageUploadError

from .base import StoredFile


DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


@dataclass(frozen=True, slots=True)
class GoogleDriveConfig:
    """Configuração mínima e sem valores hardcoded para o Google Drive."""

    folder_id: str
    credentials_path: Path | None = None
    credentials_json: str | None = None

    def validate(self) -> None:
        if not self.folder_id.strip():
            raise StorageConfigurationError(
                "GOOGLE_DRIVE_FOLDER_ID não foi configurada."
            )
        configured_sources = sum(
            (
                self.credentials_path is not None,
                bool(self.credentials_json),
            )
        )
        if configured_sources != 1:
            raise StorageConfigurationError(
                "Configure exatamente uma fonte de credenciais do Google Drive."
            )
        if self.credentials_path is not None and not self.credentials_path.is_file():
            raise StorageConfigurationError(
                "O arquivo indicado por GOOGLE_APPLICATION_CREDENTIALS não existe."
            )


class GoogleDriveStorage:
    """Armazena arquivos em uma pasta previamente autorizada no Google Drive."""

    provider = "google_drive"

    def __init__(
        self,
        config: GoogleDriveConfig,
        logger: logging.Logger,
        *,
        service_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.logger = logger
        self._service_factory = service_factory or self._default_service_factory
        self._service: Any | None = None

    def ensure_directory(self, path: tuple[str, ...]) -> str:
        """Cria ou reutiliza uma hierarquia abaixo da pasta configurada."""
        parent_id = self.config.folder_id
        for name in path:
            clean_name = name.strip()
            if not clean_name:
                raise StorageConfigurationError(
                    "A hierarquia do Google Drive contém uma pasta sem nome."
                )
            existing = self._find_folder(clean_name, parent_id)
            if existing is not None:
                parent_id = existing
                self.logger.info(
                    "storage_folder_reused",
                    extra={
                        "storage_provider": self.provider,
                        "folder_name": clean_name,
                        "storage_folder_id": parent_id,
                    },
                )
                continue
            parent_id = self._create_folder(clean_name, parent_id)
            self.logger.info(
                "storage_folder_created",
                extra={
                    "storage_provider": self.provider,
                    "folder_name": clean_name,
                    "storage_folder_id": parent_id,
                },
            )
        return parent_id

    def store_file(
        self,
        source: Path,
        *,
        object_name: str | None = None,
        content_type: str | None = None,
        directory_id: str | None = None,
    ) -> StoredFile:
        """Envia um arquivo quando chamado explicitamente por uma futura integração."""
        if not source.is_file():
            raise StorageUploadError(f"Arquivo local não encontrado: {source.name}.")

        remote_name = object_name or source.name
        media_type = content_type or mimetypes.guess_type(source.name)[0]
        media = MediaFileUpload(
            str(source),
            mimetype=media_type or "application/octet-stream",
            resumable=True,
        )
        metadata = {
            "name": remote_name,
            "parents": [directory_id or self.config.folder_id],
        }
        self.logger.info(
            "storage_upload_started",
            extra={
                "storage_provider": self.provider,
                "file_name": remote_name,
                "file_size": source.stat().st_size,
            },
        )
        try:
            payload = (
                self._drive()
                .files()
                .create(
                    body=metadata,
                    media_body=media,
                    fields="id,name,webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except (GoogleAuthError, HttpError, OSError, TypeError, ValueError) as error:
            self.logger.error(
                "storage_upload_failed",
                extra={
                    "storage_provider": self.provider,
                    "file_name": remote_name,
                    "error_type": type(error).__name__,
                },
            )
            raise StorageUploadError(
                f"Não foi possível armazenar {remote_name} no Google Drive."
            ) from error

        file_id = str(payload.get("id") or "").strip()
        if not file_id:
            raise StorageUploadError(
                "O Google Drive não retornou o identificador do arquivo armazenado."
            )
        stored = StoredFile(
            provider=self.provider,
            file_id=file_id,
            name=str(payload.get("name") or remote_name),
            web_url=str(payload.get("webViewLink") or "") or None,
        )
        self.logger.info(
            "storage_upload_completed",
            extra={
                "storage_provider": self.provider,
                "file_name": stored.name,
                "storage_file_id": stored.file_id,
            },
        )
        return stored

    def _find_folder(self, name: str, parent_id: str) -> str | None:
        escaped_name = self._escape_query_value(name)
        escaped_parent = self._escape_query_value(parent_id)
        query = (
            f"name = '{escaped_name}' and "
            f"'{escaped_parent}' in parents and "
            f"mimeType = '{DRIVE_FOLDER_MIME_TYPE}' and trashed = false"
        )
        try:
            payload = (
                self._drive()
                .files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="files(id,name)",
                    pageSize=10,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
        except (GoogleAuthError, HttpError, OSError, TypeError, ValueError) as error:
            raise StorageUploadError(
                f"Não foi possível localizar a pasta {name} no Google Drive."
            ) from error
        folders = payload.get("files") or []
        identifiers = sorted(
            str(folder.get("id") or "").strip()
            for folder in folders
            if str(folder.get("id") or "").strip()
        )
        return identifiers[0] if identifiers else None

    def _create_folder(self, name: str, parent_id: str) -> str:
        metadata = {
            "name": name,
            "mimeType": DRIVE_FOLDER_MIME_TYPE,
            "parents": [parent_id],
        }
        try:
            payload = (
                self._drive()
                .files()
                .create(
                    body=metadata,
                    fields="id,name",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except (GoogleAuthError, HttpError, OSError, TypeError, ValueError) as error:
            raise StorageUploadError(
                f"Não foi possível criar a pasta {name} no Google Drive."
            ) from error
        folder_id = str(payload.get("id") or "").strip()
        if not folder_id:
            raise StorageUploadError(
                f"O Google Drive não retornou o identificador da pasta {name}."
            )
        return folder_id

    @staticmethod
    def _escape_query_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def _drive(self) -> Any:
        if self._service is None:
            self._service = self._service_factory(self._credentials())
        return self._service

    def _credentials(self) -> Any:
        try:
            if self.config.credentials_json:
                payload = json.loads(self.config.credentials_json)
            else:
                credentials_path = self.config.credentials_path
                if credentials_path is None:
                    raise StorageConfigurationError(
                        "Credenciais do Google Drive não configuradas."
                    )
                payload = json.loads(credentials_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise StorageConfigurationError(
                "As credenciais do Google Drive não contêm um JSON válido."
            ) from error

        if not isinstance(payload, dict):
            raise StorageConfigurationError(
                "As credenciais do Google Drive devem ser um objeto JSON."
            )
        credential_type = str(payload.get("type") or "").casefold()
        try:
            if credential_type == "service_account":
                return service_account.Credentials.from_service_account_info(
                    payload,
                    scopes=(DRIVE_FILE_SCOPE,),
                )
            if credential_type == "authorized_user":
                return UserCredentials.from_authorized_user_info(
                    payload,
                    scopes=(DRIVE_FILE_SCOPE,),
                )
        except (ValueError, TypeError, KeyError) as error:
            raise StorageConfigurationError(
                "As credenciais do Google Drive estão incompletas ou inválidas."
            ) from error
        raise StorageConfigurationError(
            "Tipo de credencial Google não suportado; use authorized_user "
            "ou service_account."
        )

    @staticmethod
    def _default_service_factory(credentials: Any) -> Any:
        return build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
