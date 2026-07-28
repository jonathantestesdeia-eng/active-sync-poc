"""Persistência idempotente do DataFrame homologado."""

from __future__ import annotations

from datetime import date, datetime
from dataclasses import dataclass
import sqlite3
from typing import Any

import pandas as pd

from active_sync.transformer.schema import TRANSFORMER_SCHEMA

from .database import DatabaseManager
from .exceptions import DataFramePersistenceError
from .migrations import PERFORMANCE_TABLE


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Contagens de uma carga idempotente baseada na identidade informada."""

    inserted: int = 0
    updated: int = 0
    ignored: int = 0


def _column_names() -> tuple[str, ...]:
    return tuple(column.name for column in TRANSFORMER_SCHEMA)


def _validate_frame(frame: pd.DataFrame) -> None:
    expected = _column_names()
    actual = tuple(str(column) for column in frame.columns)
    if actual != expected:
        raise DataFramePersistenceError(
            "O DataFrame não respeita os nomes e a ordem do schema oficial. "
            f"Esperado: {list(expected)}; recebido: {list(actual)}."
        )
    duplicated = frame.columns[frame.columns.duplicated()].tolist()
    if duplicated:
        raise DataFramePersistenceError(
            f"O DataFrame contém colunas duplicadas: {duplicated}."
        )
    for column in TRANSFORMER_SCHEMA:
        if not column.nullable and frame[column.name].isna().any():
            raise DataFramePersistenceError(
                f"A coluna obrigatória {column.name!r} contém valores nulos."
            )


def _sqlite_value(value: Any, sqlite_type: str) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if sqlite_type == "TEXT" and isinstance(value, (date, datetime)):
        return (
            value.date().isoformat()
            if isinstance(value, datetime)
            else value.isoformat()
        )
    if sqlite_type == "INTEGER" and isinstance(value, bool):
        return int(value)
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def _insert_sql() -> str:
    columns = tuple(column.name for column in TRANSFORMER_SCHEMA)
    quoted = ", ".join(f'"{name}"' for name in columns)
    placeholders = ", ".join("?" for _ in columns)
    identity = " AND ".join(f'"{name}" IS ?' for name in columns)
    return (
        f'INSERT INTO "{PERFORMANCE_TABLE}" ({quoted}) '
        f"SELECT {placeholders} WHERE NOT EXISTS ("
        f'SELECT 1 FROM "{PERFORMANCE_TABLE}" WHERE {identity}'
        ")"
    )


def persist_dataframe(frame: pd.DataFrame, database: DatabaseManager) -> int:
    """Persiste linhas ainda inexistentes e retorna quantas foram inseridas."""
    _validate_frame(frame)
    sql = _insert_sql()
    inserted = 0
    try:
        with database.transaction():
            for row in frame.itertuples(index=False, name=None):
                values = tuple(
                    _sqlite_value(value, column.sqlite_type)
                    for value, column in zip(row, TRANSFORMER_SCHEMA, strict=True)
                )
                cursor = database.execute(sql, values + values)
                inserted += max(cursor.rowcount, 0)
    except DataFramePersistenceError:
        raise
    except sqlite3.Error as error:
        raise DataFramePersistenceError(
            "Falha ao persistir o DataFrame em performance_entrega."
        ) from error
    return inserted


def merge_dataframe(
    frame: pd.DataFrame,
    database: DatabaseManager,
    *,
    key_columns: tuple[str, ...] = ("Nota Fiscal",),
) -> MergeResult:
    """Insere, atualiza ou ignora linhas sem duplicar sua identidade lógica."""
    _validate_frame(frame)
    columns = _column_names()
    unknown_keys = tuple(key for key in key_columns if key not in columns)
    if not key_columns or unknown_keys:
        raise DataFramePersistenceError(
            f"Chaves de merge inválidas: {list(unknown_keys or key_columns)}."
        )
    if frame.loc[:, list(key_columns)].isna().any(axis=None):
        raise DataFramePersistenceError("As chaves de merge não podem ser nulas.")
    if frame.duplicated(subset=list(key_columns), keep=False).any():
        raise DataFramePersistenceError("O DataFrame contém chaves de merge duplicadas.")

    quoted_columns = ", ".join(f'"{name}"' for name in columns)
    key_where = " AND ".join(f'"{name}" IS ?' for name in key_columns)
    insert_placeholders = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(f'"{name}" = ?' for name in columns)
    key_indexes = tuple(columns.index(key) for key in key_columns)
    inserted = updated = ignored = 0

    try:
        with database.transaction():
            for row in frame.itertuples(index=False, name=None):
                values = tuple(
                    _sqlite_value(value, column.sqlite_type)
                    for value, column in zip(row, TRANSFORMER_SCHEMA, strict=True)
                )
                keys = tuple(values[index] for index in key_indexes)
                existing = database.execute(
                    f'SELECT {quoted_columns} FROM "{PERFORMANCE_TABLE}" WHERE {key_where}',
                    keys,
                ).fetchall()
                if len(existing) > 1:
                    raise DataFramePersistenceError(
                        "A base contém mais de um registro para a mesma chave de merge."
                    )
                if not existing:
                    database.execute(
                        f'INSERT INTO "{PERFORMANCE_TABLE}" ({quoted_columns}) '
                        f"VALUES ({insert_placeholders})",
                        values,
                    )
                    inserted += 1
                elif tuple(existing[0][name] for name in columns) == values:
                    ignored += 1
                else:
                    database.execute(
                        f'UPDATE "{PERFORMANCE_TABLE}" SET {update_assignments} '
                        f"WHERE {key_where}",
                        values + keys,
                    )
                    updated += 1
    except DataFramePersistenceError:
        raise
    except sqlite3.Error as error:
        raise DataFramePersistenceError(
            "Falha ao mesclar o DataFrame em performance_entrega."
        ) from error
    return MergeResult(inserted=inserted, updated=updated, ignored=ignored)
