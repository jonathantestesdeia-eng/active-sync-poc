from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from active_sync.persistence import (
    DatabaseConnectionError,
    DatabaseManager,
    DataFramePersistenceError,
    MigrationError,
    MigrationManager,
    merge_dataframe,
    persist_dataframe,
)
from active_sync.transformer.schema import TRANSFORMER_SCHEMA


def _valid_frame() -> pd.DataFrame:
    values: dict[str, object] = {
        column.name: None for column in TRANSFORMER_SCHEMA
    }
    values.update(
        {
            "CNPJ": "01234567000189",
            "Destinatário": "Cliente Teste",
            "Nota Fiscal": "000123",
            "Valor Frete": 42.5,
            "Saída": pd.Timestamp("2026-07-20"),
            "Previsão": pd.Timestamp("2026-07-21"),
            "Entrega": pd.Timestamp("2026-07-21"),
            "Flag Devolução NF": False,
            "Prazo": "NO PRAZO",
            "Data": "julho",
            "Ano": 2026,
            "Prazo2": "NO PRAZO",
            "Data3": "julho",
            "Ano4": 2026,
            "Situação": "ENTREGUE",
        }
    )
    return pd.DataFrame([values], columns=[column.name for column in TRANSFORMER_SCHEMA])


def test_database_and_table_are_created_from_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "active_sync.sqlite3"
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        columns = database.execute(
            'PRAGMA table_info("performance_entrega")'
        ).fetchall()

    assert database_path.exists()
    assert [row["name"] for row in columns] == [
        column.name for column in TRANSFORMER_SCHEMA
    ]
    assert [row["type"] for row in columns] == [
        column.sqlite_type for column in TRANSFORMER_SCHEMA
    ]


def test_migration_is_repeatable(tmp_path: Path) -> None:
    with DatabaseManager(tmp_path / "repeat.sqlite3") as database:
        migrations = MigrationManager(database)
        migrations.migrate()
        migrations.migrate()
        count = database.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'performance_entrega'"
        ).fetchone()[0]

    assert count == 1


def test_migration_detects_schema_drift(tmp_path: Path) -> None:
    with DatabaseManager(tmp_path / "drift.sqlite3") as database:
        database.execute('CREATE TABLE "performance_entrega" ("CNPJ" TEXT)')
        database.commit()
        with pytest.raises(MigrationError, match="diverge do schema"):
            MigrationManager(database).migrate()


def test_dataframe_is_persisted_with_sqlite_types_and_nulls(tmp_path: Path) -> None:
    with DatabaseManager(tmp_path / "persist.sqlite3") as database:
        MigrationManager(database).migrate()
        inserted = persist_dataframe(_valid_frame(), database)
        row = database.execute(
            'SELECT * FROM "performance_entrega"'
        ).fetchone()

    assert inserted == 1
    assert row["CNPJ"] == "01234567000189"
    assert row["Valor Frete"] == 42.5
    assert row["Entrega"] == "2026-07-21"
    assert row["Flag Devolução NF"] == 0
    assert row["Ano"] == 2026
    assert row["Cidade Origem"] is None


def test_repeating_same_load_is_idempotent_even_with_nulls(tmp_path: Path) -> None:
    second = _valid_frame()
    second.loc[0, "Nota Fiscal"] = "000124"
    frame = pd.concat(
        [_valid_frame(), second, _valid_frame()], ignore_index=True
    )
    with DatabaseManager(tmp_path / "idempotent.sqlite3") as database:
        MigrationManager(database).migrate()
        first_inserted = persist_dataframe(frame, database)
        second_inserted = persist_dataframe(frame, database)
        count = database.execute(
            'SELECT COUNT(*) FROM "performance_entrega"'
        ).fetchone()[0]

    assert first_inserted == 2
    assert second_inserted == 0
    assert count == 2


def test_merge_inserts_updates_and_ignores_by_invoice(tmp_path: Path) -> None:
    database_path = tmp_path / "merge.sqlite3"
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        first = merge_dataframe(_valid_frame(), database)
        same = merge_dataframe(_valid_frame(), database)
        changed = _valid_frame()
        changed.loc[0, "Situação"] = "ENTREGUE COM ATRASO"
        third = merge_dataframe(changed, database)
        rows = database.execute(
            'SELECT "Nota Fiscal", "Situação" FROM "performance_entrega"'
        ).fetchall()

    assert (first.inserted, first.updated, first.ignored) == (1, 0, 0)
    assert (same.inserted, same.updated, same.ignored) == (0, 0, 1)
    assert (third.inserted, third.updated, third.ignored) == (0, 1, 0)
    assert len(rows) == 1
    assert rows[0]["Situação"] == "ENTREGUE COM ATRASO"


def test_merge_rejects_duplicate_or_null_invoice_keys(tmp_path: Path) -> None:
    duplicate = pd.concat([_valid_frame(), _valid_frame()], ignore_index=True)
    missing = _valid_frame()
    missing.loc[0, "Nota Fiscal"] = None
    with DatabaseManager(tmp_path / "merge-invalid.sqlite3") as database:
        MigrationManager(database).migrate()
        with pytest.raises(DataFramePersistenceError, match="duplicadas"):
            merge_dataframe(duplicate, database)
        with pytest.raises(DataFramePersistenceError, match="não podem ser nulas"):
            merge_dataframe(missing, database)


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    with DatabaseManager(tmp_path / "rollback.sqlite3") as database:
        database.execute("CREATE TABLE rollback_test (value TEXT)")
        database.commit()
        with pytest.raises(RuntimeError, match="interromper"):
            with database.transaction():
                database.execute(
                    "INSERT INTO rollback_test (value) VALUES (?)", ("x",)
                )
                raise RuntimeError("interromper")
        count = database.execute("SELECT COUNT(*) FROM rollback_test").fetchone()[0]

    assert count == 0


def test_context_manager_closes_connection(tmp_path: Path) -> None:
    database = DatabaseManager(tmp_path / "close.sqlite3")
    with database:
        assert isinstance(database.connection, sqlite3.Connection)
    with pytest.raises(DatabaseConnectionError, match="não está aberta"):
        _ = database.connection


def test_invalid_dataframe_contract_is_rejected(tmp_path: Path) -> None:
    invalid = _valid_frame().drop(columns=["Situação"])
    with DatabaseManager(tmp_path / "invalid.sqlite3") as database:
        MigrationManager(database).migrate()
        with pytest.raises(DataFramePersistenceError, match="schema oficial"):
            persist_dataframe(invalid, database)


def test_null_in_required_column_is_rejected(tmp_path: Path) -> None:
    invalid = _valid_frame()
    invalid.loc[0, "Situação"] = None
    with DatabaseManager(tmp_path / "required.sqlite3") as database:
        MigrationManager(database).migrate()
        with pytest.raises(DataFramePersistenceError, match="Situação"):
            persist_dataframe(invalid, database)


def test_persistence_dependency_boundary() -> None:
    root = Path(__file__).parents[1] / "active_sync"
    for path in (root / "transformer").glob("*.py"):
        assert "active_sync.persistence" not in path.read_text(encoding="utf-8")

    for path in (root / "persistence").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        transformer_imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("active_sync.transformer")
        }
        assert transformer_imports <= {"active_sync.transformer.schema"}
