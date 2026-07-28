from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from active_sync.repository import (
    PerformanceEntrega,
    PerformanceFilters,
    PerformanceRepository,
    RepositoryError,
)
from active_sync.services import (
    CategoryCount,
    DashboardError,
    DashboardService,
    PerformanceQuery,
    PerformanceService,
    ServiceError,
)


def _record(
    nota_fiscal: str,
    transportadora: str | None,
    uf: str | None,
    cidade: str | None,
) -> PerformanceEntrega:
    values = {name: None for name in PerformanceEntrega.columns}
    values.update(
        {
            "Nota Fiscal": nota_fiscal,
            "Transportadora": transportadora,
            "UF Destino": uf,
            "Cidade Destino": cidade,
            "Flag Devolução NF": False,
            "Prazo": "EM ABERTO",
            "Prazo2": "EM ABERTO",
            "Situação": "EM ABERTO",
        }
    )
    return PerformanceEntrega.from_mapping(values)


def _repository_mock() -> MagicMock:
    return MagicMock(spec=PerformanceRepository)


def test_performance_service_listar_translates_public_query() -> None:
    repository = _repository_mock()
    records = [_record("NF-1", "TRANS A", "SP", "SAO PAULO")]
    repository.listar.return_value = records
    service = PerformanceService(repository)
    query = PerformanceQuery(
        transportadora="TRANS A",
        uf_destino="SP",
        periodo_inicio="2026-07-01",
        periodo_fim="2026-07-31",
        limit=25,
        offset=50,
        order_by="Saída",
        descending=True,
    )

    assert service.listar(query) == records
    repository.listar.assert_called_once_with(
        PerformanceFilters(
            transportadora="TRANS A",
            uf_destino="SP",
            periodo_inicio="2026-07-01",
            periodo_fim="2026-07-31",
        ),
        limit=25,
        offset=50,
        order_by="Saída",
        descending=True,
    )


def test_performance_service_delegates_specialized_queries() -> None:
    repository = _repository_mock()
    record = _record("NF-1", "TRANS A", "SP", "SAO PAULO")
    for method_name in (
        "buscar_por_nf",
        "buscar_por_transportadora",
        "buscar_por_periodo",
        "buscar_atrasadas",
        "buscar_em_aberto",
        "buscar_devolvidas",
    ):
        getattr(repository, method_name).return_value = [record]
    repository.contar.return_value = 1
    service = PerformanceService(repository)

    assert service.buscar_nf("NF-1") == [record]
    assert service.buscar_transportadora("TRANS A", limit=10, offset=2) == [record]
    assert service.buscar_periodo("2026-07-01", "2026-07-31", limit=5) == [record]
    assert service.buscar_atrasadas() == [record]
    assert service.buscar_em_aberto() == [record]
    assert service.buscar_devolvidas() == [record]
    assert service.contar(PerformanceQuery(situacao="EM ABERTO")) == 1

    repository.buscar_por_nf.assert_called_once_with("NF-1")
    repository.buscar_por_transportadora.assert_called_once_with(
        "TRANS A", limit=10, offset=2
    )
    repository.buscar_por_periodo.assert_called_once_with(
        "2026-07-01", "2026-07-31", limit=5, offset=0
    )
    repository.buscar_atrasadas.assert_called_once_with()
    repository.buscar_em_aberto.assert_called_once_with()
    repository.buscar_devolvidas.assert_called_once_with()
    repository.contar.assert_called_once_with(
        PerformanceFilters(situacao="EM ABERTO")
    )


def test_performance_service_translates_repository_error() -> None:
    repository = _repository_mock()
    repository.contar.side_effect = RepositoryError("falha interna")

    with pytest.raises(ServiceError, match="concluir a consulta"):
        PerformanceService(repository).contar()


def test_dashboard_totals_delegate_to_repository() -> None:
    repository = _repository_mock()
    repository.contar.side_effect = [5, 2]
    repository.buscar_atrasadas.return_value = [object()]
    repository.buscar_em_aberto.return_value = [object(), object()]
    repository.buscar_devolvidas.return_value = [object()]
    dashboard = DashboardService(repository)

    assert dashboard.total_registros() == 5
    assert dashboard.total_entregues() == 2
    assert dashboard.total_atrasadas() == 1
    assert dashboard.total_em_aberto() == 2
    assert dashboard.total_devolvidas() == 1
    assert repository.contar.call_args_list == [
        call(),
        call(PerformanceFilters(situacao="ENTREGUE")),
    ]


def test_dashboard_percentages() -> None:
    repository = _repository_mock()
    dashboard = DashboardService(repository)

    repository.buscar_atrasadas.return_value = [object()]
    repository.contar.return_value = 4
    assert dashboard.percentual_atraso() == 25.0

    repository.contar.side_effect = [3, 4]
    assert dashboard.percentual_entregues() == 75.0

    repository.contar.side_effect = None
    repository.contar.return_value = 4
    repository.buscar_devolvidas.return_value = [object()]
    assert dashboard.percentual_devolvidas() == 25.0


def test_empty_dashboard_percentages_are_zero() -> None:
    repository = _repository_mock()
    repository.contar.return_value = 0
    repository.buscar_atrasadas.return_value = []
    repository.buscar_devolvidas.return_value = []
    dashboard = DashboardService(repository)

    assert dashboard.percentual_atraso() == 0.0
    assert dashboard.percentual_entregues() == 0.0
    assert dashboard.percentual_devolvidas() == 0.0


def test_dashboard_distributions_return_dtos() -> None:
    repository = _repository_mock()
    repository.listar.return_value = [
        _record("NF-1", "TRANS B", "SP", "SAO PAULO"),
        _record("NF-2", "TRANS A", "SP", "CAMPINAS"),
        _record("NF-3", " TRANS B ", "MG", "BELO HORIZONTE"),
        _record("NF-4", None, None, ""),
    ]
    dashboard = DashboardService(repository)

    assert dashboard.transportadoras() == (
        CategoryCount("TRANS B", 2),
        CategoryCount("TRANS A", 1),
    )
    assert dashboard.ufs() == (
        CategoryCount("SP", 2),
        CategoryCount("MG", 1),
    )
    assert dashboard.cidades() == (
        CategoryCount("BELO HORIZONTE", 1),
        CategoryCount("CAMPINAS", 1),
        CategoryCount("SAO PAULO", 1),
    )


def test_dashboard_translates_repository_error() -> None:
    repository = _repository_mock()
    repository.listar.side_effect = RepositoryError("falha interna")

    with pytest.raises(DashboardError, match="indicadores"):
        DashboardService(repository).transportadoras()


def test_services_architectural_boundary() -> None:
    root = Path(__file__).parents[1] / "active_sync"
    forbidden_imports = {
        "sqlite3",
        "pandas",
        "openpyxl",
        "active_sync.persistence",
        "active_sync.transformer",
    }
    forbidden_sql = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ")
    for path in (root / "services").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not imported.intersection(forbidden_imports)
        assert not any(fragment in text.upper() for fragment in forbidden_sql)

    for directory in ("repository", "persistence", "transformer"):
        for path in (root / directory).glob("*.py"):
            assert "active_sync.services" not in path.read_text(encoding="utf-8")
