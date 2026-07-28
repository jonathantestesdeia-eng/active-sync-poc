"""Consultas operacionais do SuperTrack, separadas de Performance Entrega."""

from __future__ import annotations

from active_sync.persistence import (
    DatabaseManager,
    SUPERTRACK_COLUMNS,
    SUPERTRACK_TABLE,
)

from .exceptions import RepositoryError
from .models import SuperTrackMovement


_SELECT_COLUMNS = ", ".join(f'"{name}"' for name in SUPERTRACK_COLUMNS)


class SuperTrackRepository:
    """Lê todos os movimentos relacionados a uma Nota Fiscal."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def buscar_por_nf(self, nota_fiscal: str) -> list[SuperTrackMovement]:
        sql = f'''SELECT {_SELECT_COLUMNS} FROM "{SUPERTRACK_TABLE}"
        WHERE nota_fiscal = ?
        ORDER BY emissao ASC, serie_cte ASC, cte ASC'''
        try:
            rows = self.database.execute(sql, (nota_fiscal,)).fetchall()
        except Exception as error:
            raise RepositoryError(
                "Falha ao consultar movimentos do SuperTrack."
            ) from error
        return [SuperTrackMovement.from_mapping(row) for row in rows]
