"""Serviço operacional de consulta por Nota Fiscal."""

from __future__ import annotations

from active_sync.repository import (
    RepositoryError,
    SuperTrackMovement,
    SuperTrackRepository,
)

from .exceptions import ServiceError


class SuperTrackService:
    def __init__(self, repository: SuperTrackRepository) -> None:
        self.repository = repository

    def buscar_nf(self, nota_fiscal: str) -> list[SuperTrackMovement]:
        try:
            return self.repository.buscar_por_nf(nota_fiscal.strip())
        except RepositoryError as error:
            raise ServiceError(
                "Não foi possível consultar os movimentos da Nota Fiscal."
            ) from error
