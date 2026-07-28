"""Criação e validação da estrutura persistente."""

from __future__ import annotations

import sqlite3

from active_sync.transformer.schema import TRANSFORMER_SCHEMA, sqlite_ddl

from .database import DatabaseManager
from .exceptions import MigrationError


PERFORMANCE_TABLE = "performance_entrega"
SUPERTRACK_TABLE = "supertrack_movements"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"
SUPERTRACK_MIGRATION = "002_supertrack_movements"
HISTORICAL_BASE_MIGRATION = "003_historical_consolidation"

SUPERTRACK_DDL = f'''
CREATE TABLE IF NOT EXISTS "{SUPERTRACK_TABLE}" (
    transportador_id TEXT NOT NULL,
    serie_cte TEXT NOT NULL,
    cte TEXT NOT NULL,
    nota_fiscal TEXT NOT NULL,
    chave_cte TEXT,
    serie_nf TEXT,
    pedido TEXT,
    tipo_cte TEXT,
    transportadora TEXT,
    remetente TEXT,
    destinatario TEXT,
    cnpj_destinatario TEXT,
    cidade_origem TEXT,
    cidade_destino TEXT,
    uf_destino TEXT,
    emissao TEXT,
    saida TEXT,
    previsao TEXT,
    entrega TEXT,
    situacao TEXT NOT NULL,
    observacao TEXT,
    valor_frete REAL,
    data_atualizacao TEXT,
    last_seen_request_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_sync_id TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transportador_id, serie_cte, cte, nota_fiscal)
)
'''


class MigrationManager:
    """Aplica migrações derivadas exclusivamente do contrato oficial."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def migrate(self) -> None:
        """Preserva Performance e aplica migrações aditivas versionadas."""
        ddl = sqlite_ddl(PERFORMANCE_TABLE).replace(
            "CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1
        )
        try:
            with self.database.transaction():
                self.database.execute(ddl)
                self.database.execute(
                    f'''CREATE TABLE IF NOT EXISTS "{SCHEMA_MIGRATIONS_TABLE}" (
                        migration_id TEXT PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )'''
                )
                self.database.execute(SUPERTRACK_DDL)
                self._ensure_supertrack_metadata()
                self.database.execute(
                    f'''CREATE INDEX IF NOT EXISTS
                    idx_supertrack_movements_nota_fiscal
                    ON "{SUPERTRACK_TABLE}" (nota_fiscal)'''
                )
                self.database.execute(
                    f'''INSERT OR IGNORE INTO "{SCHEMA_MIGRATIONS_TABLE}"
                    (migration_id) VALUES (?)''',
                    (SUPERTRACK_MIGRATION,),
                )
                self.database.execute(
                    f'''INSERT OR IGNORE INTO "{SCHEMA_MIGRATIONS_TABLE}"
                    (migration_id) VALUES (?)''',
                    (HISTORICAL_BASE_MIGRATION,),
                )
            self._validate_schema()
            self._validate_supertrack_schema()
        except MigrationError:
            raise
        except sqlite3.Error as error:
            raise MigrationError("Falha ao aplicar a migração SQLite.") from error
        except Exception as error:
            raise MigrationError("Falha ao aplicar a migração SQLite.") from error

    def _ensure_supertrack_metadata(self) -> None:
        columns = {
            str(row["name"])
            for row in self.database.execute(
                f'PRAGMA table_info("{SUPERTRACK_TABLE}")'
            ).fetchall()
        }
        for column_name in (
            "first_seen_at",
            "last_seen_at",
            "last_sync_id",
            "updated_at",
            "created_at",
        ):
            if column_name not in columns:
                self.database.execute(
                    f'ALTER TABLE "{SUPERTRACK_TABLE}" ADD COLUMN "{column_name}" TEXT'
                )
        self.database.execute(
            f'''UPDATE "{SUPERTRACK_TABLE}" SET
                first_seen_at = COALESCE(first_seen_at, CURRENT_TIMESTAMP),
                last_seen_at = COALESCE(last_seen_at, CURRENT_TIMESTAMP),
                last_sync_id = COALESCE(last_sync_id, last_seen_request_id),
                updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP),
                created_at = COALESCE(created_at, CURRENT_TIMESTAMP)'''
        )

    def _validate_schema(self) -> None:
        rows = self.database.execute(
            f'PRAGMA table_info("{PERFORMANCE_TABLE}")'
        ).fetchall()
        actual = [
            (str(row["name"]), str(row["type"]), not bool(row["notnull"]))
            for row in rows
        ]
        expected = [
            (column.name, column.sqlite_type, column.nullable)
            for column in TRANSFORMER_SCHEMA
        ]
        if actual != expected:
            raise MigrationError(
                "A tabela performance_entrega diverge do schema oficial. "
                f"Esperado: {expected}; recebido: {actual}."
            )

    def _validate_supertrack_schema(self) -> None:
        expected_key = ["transportador_id", "serie_cte", "cte", "nota_fiscal"]
        rows = self.database.execute(
            f'PRAGMA table_info("{SUPERTRACK_TABLE}")'
        ).fetchall()
        primary_key = [
            str(row["name"])
            for row in sorted(rows, key=lambda item: int(item["pk"]))
            if int(row["pk"]) > 0
        ]
        if primary_key != expected_key:
            raise MigrationError(
                "A chave operacional do SuperTrack diverge do contrato. "
                f"Esperado: {expected_key}; recebido: {primary_key}."
            )
        required_metadata = {
            "first_seen_at",
            "last_seen_at",
            "last_sync_id",
            "updated_at",
            "created_at",
        }
        actual_columns = {str(row["name"]) for row in rows}
        if not required_metadata.issubset(actual_columns):
            missing = sorted(required_metadata - actual_columns)
            raise MigrationError(
                f"A tabela SuperTrack não contém metadados históricos: {missing}."
            )
