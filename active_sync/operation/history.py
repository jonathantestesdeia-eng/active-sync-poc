"""Historico persistente e independente de Repository/Services."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sqlite3

from active_sync.persistence import DatabaseManager
from active_sync.config import ProcessingProfile

from .models import SyncCommand, SyncHistoryEntry, SyncMode, SyncOrigin, SyncResult, SyncStatus


SYNC_HISTORY_TABLE = "sync_execution"
LEGACY_SYNC_HISTORY_TABLE = "sync_history"
INTERRUPTED_BY_RESTART_MESSAGE = "Sincronização interrompida por reinício da aplicação."


class SyncHistoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        with DatabaseManager(self.database_path) as database:
            database.execute(
                f'''CREATE TABLE IF NOT EXISTS "{SYNC_HISTORY_TABLE}" (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL UNIQUE,
                    data_inicio TEXT,
                    data_fim TEXT,
                    modo TEXT NOT NULL,
                    arquivo TEXT NOT NULL DEFAULT '[]',
                    inicio TEXT NOT NULL,
                    fim TEXT,
                    tempo_execucao REAL,
                    status TEXT NOT NULL,
                    linhas_lidas INTEGER NOT NULL DEFAULT 0,
                    linhas_inseridas INTEGER NOT NULL DEFAULT 0,
                    linhas_atualizadas INTEGER NOT NULL DEFAULT 0,
                    linhas_ignoradas INTEGER NOT NULL DEFAULT 0,
                    linhas_canceladas INTEGER NOT NULL DEFAULT 0,
                    mensagem TEXT,
                    warnings TEXT NOT NULL DEFAULT '[]',
                    messages TEXT NOT NULL DEFAULT '[]',
                    reprocess_of_id INTEGER,
                    usuario TEXT NOT NULL,
                    origem TEXT NOT NULL,
                    profile TEXT NOT NULL DEFAULT 'supertrack'
                )'''
            )
            self._ensure_operational_columns(database)
            self._migrate_legacy_history(database)
            database.commit()

    @staticmethod
    def _ensure_operational_columns(database: DatabaseManager) -> None:
        columns = {
            str(row["name"])
            for row in database.execute(
                f'PRAGMA table_info("{SYNC_HISTORY_TABLE}")'
            ).fetchall()
        }
        additions = {
            "warnings": "TEXT NOT NULL DEFAULT '[]'",
            "messages": "TEXT NOT NULL DEFAULT '[]'",
            "reprocess_of_id": "INTEGER",
        }
        for name, definition in additions.items():
            if name not in columns:
                database.execute(
                    f'ALTER TABLE "{SYNC_HISTORY_TABLE}" '
                    f'ADD COLUMN "{name}" {definition}'
                )

    @staticmethod
    def _migrate_legacy_history(database: DatabaseManager) -> None:
        legacy_exists = database.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (LEGACY_SYNC_HISTORY_TABLE,),
        ).fetchone()
        if legacy_exists is None:
            return
        columns = {
            str(row["name"])
            for row in database.execute(
                f'PRAGMA table_info("{LEGACY_SYNC_HISTORY_TABLE}")'
            ).fetchall()
        }
        profile_expression = (
            "profile" if "profile" in columns else "'performance'"
        )
        database.execute(
            f'''INSERT OR IGNORE INTO "{SYNC_HISTORY_TABLE}" (
                id, request_id, modo, inicio, fim, tempo_execucao, status,
                linhas_lidas, linhas_inseridas, linhas_atualizadas,
                linhas_ignoradas, mensagem, usuario, origem, profile
            )
            SELECT id, request_id, tipo, inicio, fim, duracao_ms, status,
                registros_lidos, registros_inseridos, registros_atualizados,
                registros_ignorados, erros, usuario, origem, {profile_expression}
            FROM "{LEGACY_SYNC_HISTORY_TABLE}"'''
        )

    def begin(self, command: SyncCommand) -> SyncHistoryEntry:
        with DatabaseManager(self.database_path) as database:
            cursor = database.execute(
                f'''INSERT INTO "{SYNC_HISTORY_TABLE}"
                    (request_id, data_inicio, data_fim, modo, arquivo, inicio,
                     status, usuario, origem, profile, reprocess_of_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    command.request_id,
                    command.start_date.isoformat() if command.start_date else None,
                    command.end_date.isoformat() if command.end_date else None,
                    command.mode.value,
                    json.dumps(
                        (command.source_file.name,) if command.source_file else (),
                        ensure_ascii=False,
                    ),
                    command.started_at.isoformat(),
                    SyncStatus.RUNNING.value,
                    command.user,
                    command.origin.value,
                    command.profile.value,
                    command.reprocess_of_id,
                ),
            )
            database.commit()
            entry_id = int(cursor.lastrowid)
        entry = self.get(entry_id)
        if entry is None:
            raise RuntimeError("Falha ao criar historico da sincronizacao.")
        return entry

    def finish(
        self,
        entry_id: int,
        status: SyncStatus,
        finished_at: datetime,
        duration_ms: float,
        result: SyncResult,
        error: str | None = None,
    ) -> None:
        with DatabaseManager(self.database_path) as database:
            database.execute(
                f'''UPDATE "{SYNC_HISTORY_TABLE}" SET
                    data_inicio = COALESCE(data_inicio, ?),
                    data_fim = COALESCE(data_fim, ?),
                    fim = ?, tempo_execucao = ?, status = ?, linhas_lidas = ?,
                    linhas_inseridas = ?, linhas_atualizadas = ?,
                    linhas_ignoradas = ?, linhas_canceladas = ?,
                    arquivo = ?, mensagem = ?, warnings = ?, messages = ?
                    WHERE id = ?''',
                (
                    result.period_start.isoformat() if result.period_start else None,
                    result.period_end.isoformat() if result.period_end else None,
                    finished_at.isoformat(),
                    duration_ms,
                    status.value,
                    result.records_read,
                    result.records_inserted,
                    result.records_updated,
                    result.records_ignored,
                    result.records_cancelled,
                    json.dumps(result.source_files, ensure_ascii=False),
                    error,
                    json.dumps(result.warnings, ensure_ascii=False),
                    json.dumps(result.messages, ensure_ascii=False),
                    entry_id,
                ),
            )
            database.commit()

    def recover_interrupted(self, finished_at: datetime) -> int:
        """Finaliza como erro as execuções abandonadas por um reinício da aplicação."""
        with DatabaseManager(self.database_path) as database:
            rows = database.execute(
                f'''SELECT id, inicio FROM "{SYNC_HISTORY_TABLE}"
                    WHERE status = ?''',
                (SyncStatus.RUNNING.value,),
            ).fetchall()
            updates = []
            for row in rows:
                started_at = datetime.fromisoformat(str(row["inicio"]))
                comparable_finished_at = finished_at
                if started_at.tzinfo is None:
                    comparable_finished_at = finished_at.replace(tzinfo=None)
                elif comparable_finished_at.tzinfo is None:
                    comparable_finished_at = comparable_finished_at.replace(
                        tzinfo=started_at.tzinfo
                    )
                else:
                    comparable_finished_at = comparable_finished_at.astimezone(
                        started_at.tzinfo
                    )
                duration_ms = max(
                    (comparable_finished_at - started_at).total_seconds() * 1000,
                    0.0,
                )
                updates.append(
                    (
                        finished_at.isoformat(),
                        duration_ms,
                        SyncStatus.ERROR.value,
                        INTERRUPTED_BY_RESTART_MESSAGE,
                        int(row["id"]),
                        SyncStatus.RUNNING.value,
                    )
                )
            if updates:
                database.executemany(
                    f'''UPDATE "{SYNC_HISTORY_TABLE}" SET
                        fim = ?, tempo_execucao = ?, status = ?, mensagem = ?
                        WHERE id = ? AND status = ?''',
                    updates,
                )
                database.commit()
        return len(updates)

    def list(self, limit: int = 100, offset: int = 0) -> tuple[SyncHistoryEntry, ...]:
        with DatabaseManager(self.database_path) as database:
            rows = database.execute(
                f'SELECT * FROM "{SYNC_HISTORY_TABLE}" ORDER BY id DESC LIMIT ? OFFSET ?',
                (limit, offset),
            ).fetchall()
        return tuple(self._entry(row) for row in rows)

    def get(self, entry_id: int) -> SyncHistoryEntry | None:
        with DatabaseManager(self.database_path) as database:
            row = database.execute(
                f'SELECT * FROM "{SYNC_HISTORY_TABLE}" WHERE id = ?', (entry_id,)
            ).fetchone()
        return self._entry(row) if row is not None else None

    def latest(self) -> SyncHistoryEntry | None:
        entries = self.list(limit=1)
        return entries[0] if entries else None

    def aggregate(self) -> dict[str, object]:
        """Calcula métricas de execução sem depender de ferramenta externa."""
        with DatabaseManager(self.database_path) as database:
            row = database.execute(
                f'''SELECT
                    COUNT(*) AS sync_count,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS failure_count,
                    AVG(tempo_execucao) AS average_duration_ms,
                    MAX(tempo_execucao) AS maximum_duration_ms,
                    MIN(tempo_execucao) AS minimum_duration_ms,
                    MIN(inicio) AS first_sync_at,
                    MAX(COALESCE(fim, inicio)) AS last_sync_at,
                    COALESCE(SUM(linhas_canceladas), 0) AS cancelled_total
                FROM "{SYNC_HISTORY_TABLE}"''',
                (SyncStatus.ERROR.value,),
            ).fetchone()
        return {
            "sync_count": int(row["sync_count"] or 0),
            "failure_count": int(row["failure_count"] or 0),
            "average_duration_ms": (
                float(row["average_duration_ms"])
                if row["average_duration_ms"] is not None
                else None
            ),
            "maximum_duration_ms": (
                float(row["maximum_duration_ms"])
                if row["maximum_duration_ms"] is not None
                else None
            ),
            "minimum_duration_ms": (
                float(row["minimum_duration_ms"])
                if row["minimum_duration_ms"] is not None
                else None
            ),
            "first_sync_at": (
                datetime.fromisoformat(row["first_sync_at"])
                if row["first_sync_at"]
                else None
            ),
            "last_sync_at": (
                datetime.fromisoformat(row["last_sync_at"])
                if row["last_sync_at"]
                else None
            ),
            "cancelled_total": int(row["cancelled_total"] or 0),
        }

    @staticmethod
    def _entry(row: sqlite3.Row) -> SyncHistoryEntry:
        return SyncHistoryEntry(
            id=int(row["id"]),
            request_id=str(row["request_id"]),
            mode=SyncMode(row["modo"]),
            started_at=datetime.fromisoformat(row["inicio"]),
            finished_at=datetime.fromisoformat(row["fim"]) if row["fim"] else None,
            duration_ms=(
                float(row["tempo_execucao"])
                if row["tempo_execucao"] is not None
                else None
            ),
            status=SyncStatus(row["status"]),
            records_read=int(row["linhas_lidas"]),
            records_inserted=int(row["linhas_inseridas"]),
            records_updated=int(row["linhas_atualizadas"]),
            records_ignored=int(row["linhas_ignoradas"]),
            errors=str(row["mensagem"]) if row["mensagem"] else None,
            user=str(row["usuario"]),
            origin=SyncOrigin(row["origem"]),
            profile=ProcessingProfile(row["profile"]),
            start_date=(
                date.fromisoformat(row["data_inicio"])
                if row["data_inicio"]
                else None
            ),
            end_date=(
                date.fromisoformat(row["data_fim"])
                if row["data_fim"]
                else None
            ),
            source_files=tuple(json.loads(row["arquivo"] or "[]")),
            records_cancelled=int(row["linhas_canceladas"]),
            warnings=tuple(json.loads(row["warnings"] or "[]")),
            messages=tuple(json.loads(row["messages"] or "[]")),
            reprocess_of_id=(
                int(row["reprocess_of_id"])
                if row["reprocess_of_id"] is not None
                else None
            ),
        )
