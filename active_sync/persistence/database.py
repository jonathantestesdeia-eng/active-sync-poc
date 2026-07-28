"""Gerenciamento de conexões e transações SQLite."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from types import TracebackType
from typing import Any, Self

from .exceptions import DatabaseConnectionError


class DatabaseManager:
    """Abre, fecha e controla transações de uma base SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = (
            Path(database_path) if database_path != ":memory:" else Path(":memory:")
        )
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Retorna a conexão aberta ou informa claramente o uso incorreto."""
        if self._connection is None:
            raise DatabaseConnectionError("A conexão com o banco não está aberta.")
        return self._connection

    def open(self) -> sqlite3.Connection:
        """Abre a conexão, criando o diretório e o arquivo quando necessário."""
        if self._connection is not None:
            return self._connection
        if self.database_path != Path(":memory:"):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._connection = sqlite3.connect(self.database_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error as error:
            raise DatabaseConnectionError(
                f"Não foi possível abrir o banco {self.database_path}."
            ) from error
        return self._connection

    def close(self) -> None:
        """Fecha a conexão aberta."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def execute(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> sqlite3.Cursor:
        """Executa uma instrução SQL na conexão atual."""
        return self.connection.execute(sql, parameters)

    def executemany(
        self,
        sql: str,
        parameters: Sequence[Sequence[Any]],
    ) -> sqlite3.Cursor:
        """Executa a mesma instrução para vários conjuntos de parâmetros."""
        return self.connection.executemany(sql, parameters)

    def commit(self) -> None:
        """Confirma a transação atual."""
        self.connection.commit()

    def rollback(self) -> None:
        """Desfaz a transação atual."""
        self.connection.rollback()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Executa um bloco atômico com commit ou rollback automático."""
        connection = self.connection
        if connection.in_transaction:
            raise DatabaseConnectionError("Já existe uma transação ativa.")
        try:
            connection.execute("BEGIN")
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._connection is not None and self._connection.in_transaction:
            self._connection.rollback()
        self.close()
