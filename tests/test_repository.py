from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from active_sync.persistence import DatabaseManager, MigrationManager, persist_dataframe
from active_sync.repository import (
    InvalidQueryError,
    PerformanceEntrega,
    PerformanceFilters,
    PerformanceRepository,
)
from active_sync.transformer.schema import TRANSFORMER_SCHEMA


def _row(
    nota_fiscal: str,
    transportadora: str,
    uf: str,
    cidade: str,
    saida: str,
    prazo: str,
    situacao: str,
    *,
    devolucao: bool = False,
) -> dict[str, object]:
    values: dict[str, object] = {
        column.name: None for column in TRANSFORMER_SCHEMA
    }
    values.update(
        {
            "Nota Fiscal": nota_fiscal,
            "Transportadora": transportadora,
            "UF Destino": uf,
            "Cidade Destino": cidade,
            "Saída": pd.Timestamp(saida),
            "Flag Devolução NF": devolucao,
            "Prazo": prazo,
            "Prazo2": prazo,
            "Situação": situacao,
        }
    )
    return values


def _populated_frame() -> pd.DataFrame:
    rows = [
        _row("NF-001", "TRANS A", "SP", "SAO PAULO", "2026-07-01", "NO PRAZO", "ENTREGUE"),
        _row("NF-002", "TRANS A", "SP", "CAMPINAS", "2026-07-02", "FORA DO PRAZO", "ATRASADA"),
        _row("NF-003", "TRANS B", "MG", "BELO HORIZONTE", "2026-07-03", "EM ABERTO", "EM ABERTO"),
        _row("NF-004", "TRANS B", "MG", "BELO HORIZONTE", "2026-07-04", "DEVOLVIDA", "DEVOLVIDA", devolucao=True),
        _row("NF-005", "TRANS C", "RJ", "RIO DE JANEIRO", "2026-08-01", "EM ABERTO", "EM ABERTO"),
    ]
    return pd.DataFrame(rows, columns=[column.name for column in TRANSFORMER_SCHEMA])


@pytest.fixture
def empty_repository(tmp_path: Path) -> PerformanceRepository:
    database = DatabaseManager(tmp_path / "empty.sqlite3")
    database.open()
    MigrationManager(database).migrate()
    repository = PerformanceRepository(database)
    try:
        yield repository
    finally:
        database.close()


@pytest.fixture
def populated_repository(tmp_path: Path) -> PerformanceRepository:
    database = DatabaseManager(tmp_path / "populated.sqlite3")
    database.open()
    MigrationManager(database).migrate()
    persist_dataframe(_populated_frame(), database)
    repository = PerformanceRepository(database)
    try:
        yield repository
    finally:
        database.close()


def test_empty_repository(empty_repository: PerformanceRepository) -> None:
    assert empty_repository.listar() == []
    assert empty_repository.contar() == 0
    assert not empty_repository.existe_nf("INEXISTENTE")


def test_domain_model_is_derived_from_schema(
    populated_repository: PerformanceRepository,
) -> None:
    record = populated_repository.buscar_por_nf("NF-001")[0]

    assert isinstance(record, PerformanceEntrega)
    assert record.columns == tuple(column.name for column in TRANSFORMER_SCHEMA)
    assert len(record.as_dict()) == 22
    assert record.nota_fiscal == "NF-001"
    assert record["Transportadora"] == "TRANS A"


def test_existing_and_missing_invoice(
    populated_repository: PerformanceRepository,
) -> None:
    assert populated_repository.existe_nf("NF-003")
    assert not populated_repository.existe_nf("NF-999")
    assert populated_repository.buscar_por_nf("NF-999") == []


def test_pagination_and_ordering(
    populated_repository: PerformanceRepository,
) -> None:
    page = populated_repository.listar(
        limit=2,
        offset=1,
        order_by="Nota Fiscal",
        descending=True,
    )

    assert [record.nota_fiscal for record in page] == ["NF-004", "NF-003"]


def test_combined_filters(populated_repository: PerformanceRepository) -> None:
    filters = PerformanceFilters(
        transportadora="TRANS B",
        uf_destino="MG",
        cidade_destino="BELO HORIZONTE",
        prazo="EM ABERTO",
        situacao="EM ABERTO",
    )

    records = populated_repository.listar(filters)
    assert [record.nota_fiscal for record in records] == ["NF-003"]
    assert populated_repository.contar(filters) == 1


def test_period_filter_is_inclusive_and_accepts_dates(
    populated_repository: PerformanceRepository,
) -> None:
    records = populated_repository.buscar_por_periodo(
        date(2026, 7, 2), "2026-07-04"
    )

    assert [record.nota_fiscal for record in records] == [
        "NF-002",
        "NF-003",
        "NF-004",
    ]


def test_transportadora_filter(populated_repository: PerformanceRepository) -> None:
    records = populated_repository.buscar_por_transportadora("TRANS A")
    assert [record.nota_fiscal for record in records] == ["NF-001", "NF-002"]


def test_operational_queries(populated_repository: PerformanceRepository) -> None:
    assert [record.nota_fiscal for record in populated_repository.buscar_atrasadas()] == ["NF-002"]
    assert [record.nota_fiscal for record in populated_repository.buscar_em_aberto()] == ["NF-003", "NF-005"]
    assert [record.nota_fiscal for record in populated_repository.buscar_devolvidas()] == ["NF-004"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit"),
        ({"offset": -1}, "offset"),
        ({"order_by": 'Nota Fiscal"; DROP TABLE x; --'}, "ordenação"),
    ],
)
def test_invalid_pagination_and_ordering_are_rejected(
    populated_repository: PerformanceRepository,
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(InvalidQueryError, match=message):
        populated_repository.listar(**kwargs)  # type: ignore[arg-type]


def test_invalid_period_is_rejected(
    populated_repository: PerformanceRepository,
) -> None:
    with pytest.raises(InvalidQueryError, match="posterior"):
        populated_repository.buscar_por_periodo("2026-08-01", "2026-07-01")
    with pytest.raises(InvalidQueryError, match="ISO"):
        populated_repository.buscar_por_periodo("01/07/2026", "2026-07-01")


def test_filter_values_are_parameterized(
    populated_repository: PerformanceRepository,
) -> None:
    malicious = "TRANS A' OR 1=1 --"
    assert populated_repository.buscar_por_transportadora(malicious) == []
    assert populated_repository.contar() == 5


def test_repository_dependency_boundary() -> None:
    root = Path(__file__).parents[1] / "active_sync"
    forbidden = {
        "active_sync.excel_reader",
        "active_sync.transformer.comparator",
        "active_sync.transformer.snapshot_validator",
        "active_sync.transformer.reconciliation",
    }
    for path in (root / "repository").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not imported.intersection(forbidden)
        transformer_imports = {
            module for module in imported if module.startswith("active_sync.transformer")
        }
        assert transformer_imports <= {"active_sync.transformer.schema"}

    for path in (root / "persistence").glob("*.py"):
        assert "active_sync.repository" not in path.read_text(encoding="utf-8")
