from __future__ import annotations

from pathlib import Path

from active_sync.transformer.columns import (
    BOOLEAN_COLUMNS,
    DATE_COLUMNS,
    NUMERIC_COLUMNS,
    OUTPUT_COLUMNS,
    TEXT_COLUMNS,
)
from active_sync.transformer.schema import (
    ColumnStatus,
    TRANSFORMER_SCHEMA,
    postgresql_ddl,
    schema_markdown,
    sqlite_ddl,
    write_schema_markdown,
)


def test_schema_is_the_single_source_of_truth_for_order_and_types() -> None:
    assert tuple(column.name for column in TRANSFORMER_SCHEMA) == OUTPUT_COLUMNS
    assert len(OUTPUT_COLUMNS) == 22
    assert len(set(OUTPUT_COLUMNS)) == 22
    assert DATE_COLUMNS == {"Saída", "Previsão", "Entrega"}
    assert NUMERIC_COLUMNS == {"Valor Frete", "Ano", "Ano4"}
    assert BOOLEAN_COLUMNS == {"Flag Devolução NF"}
    assert "Data3" in TEXT_COLUMNS
    assert "Situação" in TEXT_COLUMNS


def test_every_column_has_complete_persistence_metadata_and_classification() -> None:
    valid_statuses = set(ColumnStatus)
    for column in TRANSFORMER_SCHEMA:
        assert column.name
        assert column.pandas_dtype
        assert column.sqlite_type
        assert column.postgresql_type
        assert column.description
        assert column.source
        assert column.rule
        assert column.dependencies
        assert column.status in valid_statuses


def test_final_column_classification_has_no_provisional_rule() -> None:
    by_name = {column.name: column for column in TRANSFORMER_SCHEMA}
    assert by_name["Data3"].status is ColumnStatus.IMPLEMENTED
    assert by_name["Ano4"].status is ColumnStatus.IMPLEMENTED
    assert by_name["Flag Devolução NF"].status is ColumnStatus.PENDING_VALIDATION
    assert by_name["CTe Devolução"].status is ColumnStatus.PENDING_VALIDATION
    assert by_name["Situação"].status is ColumnStatus.PENDING_VALIDATION
    assert not any(
        column.status is ColumnStatus.NOT_IMPLEMENTED for column in TRANSFORMER_SCHEMA
    )


def test_generated_ddl_contains_all_columns_without_accessing_a_database() -> None:
    sqlite = sqlite_ddl()
    postgresql = postgresql_ddl()

    assert sqlite.startswith('CREATE TABLE "performance_entrega"')
    assert postgresql.startswith('CREATE TABLE "performance_entrega"')
    for column in TRANSFORMER_SCHEMA:
        assert f'"{column.name}" {column.sqlite_type}' in sqlite
        assert f'"{column.name}" {column.postgresql_type}' in postgresql
    assert '"Flag Devolução NF" INTEGER NOT NULL' in sqlite
    assert '"Flag Devolução NF" BOOLEAN NOT NULL' in postgresql


def test_invalid_table_name_is_rejected() -> None:
    try:
        sqlite_ddl("performance_entrega; DROP TABLE x")
    except ValueError as error:
        assert "Nome de tabela inválido" in str(error)
    else:
        raise AssertionError("O nome de tabela inseguro deveria ter sido rejeitado")


def test_schema_markdown_is_generated_from_the_contract(tmp_path: Path) -> None:
    output = write_schema_markdown(tmp_path / "SCHEMA.md")
    text = output.read_text(encoding="utf-8")

    assert text == schema_markdown()
    assert "## SQLite" in text
    assert "## PostgreSQL" in text
    assert "| 20 | Data3 | IMPLEMENTADA | object |" in text
    assert "| 21 | Ano4 | IMPLEMENTADA | Int64 |" in text
    assert "| 22 | Situação | IMPLEMENTADA COM VALIDAÇÃO PENDENTE | object |" in text
