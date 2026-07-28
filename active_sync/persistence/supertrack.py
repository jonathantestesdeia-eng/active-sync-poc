"""Persistência idempotente dos movimentos operacionais do SuperTrack."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from .database import DatabaseManager
from .exceptions import DataFramePersistenceError


SUPERTRACK_TABLE = "supertrack_movements"
SUPERTRACK_KEY_COLUMNS = (
    "transportador_id",
    "serie_cte",
    "cte",
    "nota_fiscal",
)
SUPERTRACK_COLUMNS = (
    *SUPERTRACK_KEY_COLUMNS,
    "chave_cte",
    "serie_nf",
    "pedido",
    "tipo_cte",
    "transportadora",
    "remetente",
    "destinatario",
    "cnpj_destinatario",
    "cidade_origem",
    "cidade_destino",
    "uf_destino",
    "emissao",
    "saida",
    "previsao",
    "entrega",
    "situacao",
    "observacao",
    "valor_frete",
    "data_atualizacao",
)
SQLITE_KEY_BATCH_SIZE = 200


@dataclass(frozen=True, slots=True)
class SuperTrackMergeResult:
    inserted: int = 0
    updated: int = 0
    ignored: int = 0


def _database_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def merge_supertrack_movements(
    frame: pd.DataFrame,
    database: DatabaseManager,
    *,
    request_id: str,
) -> SuperTrackMergeResult:
    """Mescla movimentos pela identidade composta sem colapsar CT-es da mesma NF."""
    if tuple(frame.columns) != SUPERTRACK_COLUMNS:
        raise DataFramePersistenceError(
            "O DataFrame operacional não respeita o contrato do SuperTrack."
        )
    if frame.loc[:, list(SUPERTRACK_KEY_COLUMNS)].isna().any(axis=None):
        raise DataFramePersistenceError("A chave operacional não pode conter nulos.")
    if frame.duplicated(subset=list(SUPERTRACK_KEY_COLUMNS), keep=False).any():
        raise DataFramePersistenceError(
            "O DataFrame operacional contém chaves compostas duplicadas."
        )

    quoted_columns = ", ".join(f'"{name}"' for name in SUPERTRACK_COLUMNS)
    placeholders = ", ".join("?" for _ in SUPERTRACK_COLUMNS)
    update_columns = tuple(
        name for name in SUPERTRACK_COLUMNS if name not in SUPERTRACK_KEY_COLUMNS
    )
    update_assignments = ", ".join(f'"{name}" = ?' for name in update_columns)
    records = [
        tuple(_database_value(value) for value in row)
        for row in frame.itertuples(index=False, name=None)
    ]
    payloads = [
        dict(zip(SUPERTRACK_COLUMNS, values, strict=True))
        for values in records
    ]
    keys = [
        tuple(payload[name] for name in SUPERTRACK_KEY_COLUMNS)
        for payload in payloads
    ]
    existing = _load_existing(database, keys, quoted_columns)
    sync_time = datetime.now(timezone.utc).isoformat()
    inserts: list[tuple[Any, ...]] = []
    updates: list[tuple[Any, ...]] = []
    touches: list[tuple[Any, ...]] = []
    for values, payload, key in zip(records, payloads, keys, strict=True):
        current = existing.get(key)
        if current is None:
            inserts.append(
                values
                + (
                    request_id,
                    sync_time,
                    sync_time,
                    request_id,
                    sync_time,
                    sync_time,
                )
            )
        elif current == values:
            touches.append((request_id, sync_time, request_id) + key)
        else:
            updated_values = tuple(payload[name] for name in update_columns)
            updates.append(
                updated_values
                + (request_id, sync_time, request_id, sync_time)
                + key
            )

    key_where = " AND ".join(f'"{name}" = ?' for name in SUPERTRACK_KEY_COLUMNS)
    with database.transaction():
        if inserts:
            database.executemany(
                f'''INSERT INTO "{SUPERTRACK_TABLE}"
                ({quoted_columns}, last_seen_request_id, first_seen_at,
                 last_seen_at, last_sync_id, updated_at, created_at)
                VALUES ({placeholders}, ?, ?, ?, ?, ?, ?)''',
                inserts,
            )
        if updates:
            database.executemany(
                f'''UPDATE "{SUPERTRACK_TABLE}" SET
                {update_assignments},
                last_seen_request_id = ?,
                last_seen_at = ?,
                last_sync_id = ?,
                updated_at = ?
                WHERE {key_where}''',
                updates,
            )
        if touches:
            database.executemany(
                f'''UPDATE "{SUPERTRACK_TABLE}" SET
                last_seen_request_id = ?,
                last_seen_at = ?,
                last_sync_id = ?
                WHERE {key_where}''',
                touches,
            )
    return SuperTrackMergeResult(len(inserts), len(updates), len(touches))


def _load_existing(
    database: DatabaseManager,
    keys: list[tuple[Any, ...]],
    quoted_columns: str,
) -> dict[tuple[Any, ...], tuple[Any, ...]]:
    existing: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    key_expression = ", ".join(f'"{name}"' for name in SUPERTRACK_KEY_COLUMNS)
    for start in range(0, len(keys), SQLITE_KEY_BATCH_SIZE):
        chunk = keys[start : start + SQLITE_KEY_BATCH_SIZE]
        if not chunk:
            continue
        row_placeholder = "(" + ", ".join("?" for _ in SUPERTRACK_KEY_COLUMNS) + ")"
        placeholders = ", ".join(row_placeholder for _ in chunk)
        parameters = tuple(value for key in chunk for value in key)
        rows = database.execute(
            f'''SELECT {quoted_columns} FROM "{SUPERTRACK_TABLE}"
            WHERE ({key_expression}) IN ({placeholders})''',
            parameters,
        ).fetchall()
        for row in rows:
            key = tuple(row[name] for name in SUPERTRACK_KEY_COLUMNS)
            existing[key] = tuple(row[name] for name in SUPERTRACK_COLUMNS)
    return existing


def delete_supertrack_movements(
    database: DatabaseManager,
    keys: tuple[tuple[str, str, str, str], ...],
) -> int:
    """Aplica tombstones de cancelamento somente às identidades recebidas."""
    if not keys:
        return 0
    unique_keys = list(dict.fromkeys(keys))
    key_expression = ", ".join(f'"{name}"' for name in SUPERTRACK_KEY_COLUMNS)
    removed = 0
    with database.transaction():
        for start in range(0, len(unique_keys), SQLITE_KEY_BATCH_SIZE):
            chunk = unique_keys[start : start + SQLITE_KEY_BATCH_SIZE]
            row_placeholder = "(" + ", ".join("?" for _ in SUPERTRACK_KEY_COLUMNS) + ")"
            placeholders = ", ".join(row_placeholder for _ in chunk)
            parameters = tuple(value for key in chunk for value in key)
            cursor = database.execute(
                f'''DELETE FROM "{SUPERTRACK_TABLE}"
                WHERE ({key_expression}) IN ({placeholders})''',
                parameters,
            )
            removed += max(cursor.rowcount, 0)
    return removed
