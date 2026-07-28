from __future__ import annotations

import ast
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from active_sync.api import create_app
from active_sync.config import AppEnvironment, ApplicationSettings
from active_sync.api.dependencies import (
    get_dashboard_service,
    get_performance_service,
    get_sync_reprocessor,
    get_sync_coordinator,
)
from active_sync.operation import (
    SyncAlreadyRunningError,
    SyncHistoryEntry,
    SyncMode,
    SyncOrigin,
    SyncStatus,
)
from active_sync.repository import InvalidQueryError, PerformanceEntrega
from active_sync.services import (
    CategoryCount,
    DashboardError,
    DashboardService,
    PerformanceQuery,
    PerformanceService,
    ServiceError,
)


def _record(nota_fiscal: str = "NF-001") -> PerformanceEntrega:
    values = {name: None for name in PerformanceEntrega.columns}
    values.update(
        {
            "CNPJ": "12345678000190",
            "Destinatário": "CLIENTE TESTE",
            "Cidade Origem": "ARUJA",
            "Cidade Destino": "SAO PAULO",
            "UF Destino": "SP",
            "Nota Fiscal": nota_fiscal,
            "Valor Frete": 42.5,
            "Saída": "2026-07-20",
            "Previsão": "2026-07-21",
            "Entrega": "2026-07-21",
            "Transportadora": "TRANS A",
            "Flag Devolução NF": False,
            "Tipo CTe": "ENTREGA NORMAL",
            "Código cliente": "CLI-1",
            "Prazo": "NO PRAZO",
            "Data": "julho",
            "Ano": 2026,
            "Prazo2": "NO PRAZO",
            "Data3": "julho",
            "Ano4": 2026,
            "Situação": "ENTREGUE",
        }
    )
    return PerformanceEntrega.from_mapping(values)


@pytest.fixture
def performance_service() -> MagicMock:
    return MagicMock(spec=PerformanceService)


@pytest.fixture
def dashboard_service() -> MagicMock:
    return MagicMock(spec=DashboardService)


@pytest.fixture
def api_settings(tmp_path: Path) -> ApplicationSettings:
    return ApplicationSettings(
        environment=AppEnvironment.TEST,
        api_key="test-api-key-123456789",
        allowed_origins=("http://localhost:5173",),
        database_path=tmp_path / "api.sqlite3",
        version="17.0.0-test",
        build_date="2026-07-22T00:00:00Z",
    )


@pytest.fixture
def client(
    performance_service: MagicMock,
    dashboard_service: MagicMock,
    api_settings: ApplicationSettings,
) -> Iterator[TestClient]:
    app = create_app(api_settings)
    app.dependency_overrides[get_performance_service] = lambda: performance_service
    app.dependency_overrides[get_dashboard_service] = lambda: dashboard_service
    with TestClient(app, headers={"X-API-Key": api_settings.api_key}) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["api"] == "ok"
    assert payload["storage"] == "ok"
    assert payload["version"] == "17.0.0-test"
    assert payload["timestamp"]


def test_health_database_version_and_info(client: TestClient) -> None:
    assert client.get("/health/database").json() == {"status": "ok", "database": "sqlite"}
    assert client.get("/health/version").json() == {
        "version": "17.0.0-test",
        "build_date": "2026-07-22T00:00:00Z",
    }
    assert client.get("/info").json() == {
        "version": "17.0.0-test",
        "environment": "test",
        "build_date": "2026-07-22T00:00:00Z",
        "database": "sqlite",
    }


def test_system_status_and_statistics(client: TestClient) -> None:
    system = client.get("/system/status")
    assert system.status_code == 200
    assert system.json()["api"] == "ok"
    assert system.json()["database"] == "ok"
    assert system.json()["active_profile"] == "supertrack"
    assert system.json()["total_records"] == 0
    assert system.json()["uptime_seconds"] >= 0

    statistics = client.get("/statistics")
    assert statistics.status_code == 200
    assert statistics.json()["total_movements"] == 0
    assert statistics.json()["total_returns"] == 0
    assert statistics.json()["total_cancelled"] == 0
    assert statistics.json()["sync_count"] == 0
    assert statistics.json()["failure_count"] == 0


def test_scheduler_configuration_is_persisted_and_restored(
    api_settings: ApplicationSettings,
) -> None:
    headers = {"X-API-Key": api_settings.api_key}
    with TestClient(create_app(api_settings), headers=headers) as scheduler_client:
        initial = scheduler_client.get("/scheduler/config")
        assert initial.status_code == 200
        assert initial.json()["enabled"] is False
        assert initial.json()["frequency"] == "DAILY"
        assert initial.json()["timezone"] == "America/Sao_Paulo"
        assert initial.json()["next_scheduled_at"] is None

        saved = scheduler_client.put(
            "/scheduler/config",
            json={"enabled": True, "time": "06:30"},
        )
        assert saved.status_code == 200
        assert saved.json()["enabled"] is True
        assert saved.json()["time"] == "06:30"
        assert saved.json()["next_scheduled_at"] is not None

        assert scheduler_client.put(
            "/scheduler/config",
            json={"enabled": True, "time": None},
        ).status_code == 422
        assert scheduler_client.put(
            "/scheduler/config",
            json={"enabled": True, "time": "25:90"},
        ).status_code == 422

    with TestClient(create_app(api_settings), headers=headers) as restored_client:
        restored = restored_client.get("/scheduler/config").json()
        assert restored["enabled"] is True
        assert restored["time"] == "06:30"
        disabled = restored_client.put(
            "/scheduler/config",
            json={"enabled": False, "time": "06:30"},
        ).json()
        assert disabled["enabled"] is False
        assert disabled["next_scheduled_at"] is None


def test_private_routes_require_api_key(api_settings: ApplicationSettings) -> None:
    with TestClient(create_app(api_settings)) as anonymous:
        response = anonymous.get("/performance")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
        assert response.headers["www-authenticate"] == "ApiKey"
        assert anonymous.get("/health").status_code == 200


def test_cors_allows_known_origin_and_blocks_unknown(client: TestClient) -> None:
    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"

    blocked = client.get("/health", headers={"Origin": "https://unknown.example"})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_sync_endpoints_are_protected_and_return_operational_contract(
    api_settings: ApplicationSettings,
) -> None:
    started_at = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    entry = SyncHistoryEntry(
        id=7,
        request_id="sync-request-7",
        mode=SyncMode.INCREMENTAL,
        started_at=started_at,
        finished_at=started_at,
        duration_ms=1500.0,
        status=SyncStatus.SUCCESS,
        records_read=10,
        records_inserted=4,
        records_updated=2,
        records_ignored=4,
        errors=None,
        user="operador",
        origin=SyncOrigin.MANUAL,
    )

    class FakeCoordinator:
        async def start(self, mode, **kwargs):
            self.mode = mode
            self.kwargs = kwargs
            return entry

        def list_history(self, limit, offset):
            return (entry,)

        def get_history(self, entry_id):
            return entry if entry_id == 7 else None

        def status(self):
            return {
                "running": False,
                "current": None,
                "latest": entry,
                "next_scheduled_at": datetime(2026, 7, 22, 18, tzinfo=timezone.utc),
            }

    fake = FakeCoordinator()
    app = create_app(api_settings)
    app.dependency_overrides[get_sync_coordinator] = lambda: fake
    with TestClient(app, headers={"X-API-Key": api_settings.api_key}) as sync_client:
        started = sync_client.post("/sync/run", json={"mode": "INCREMENTAL"})
        assert started.status_code == 202
        assert started.json()["request_id"] == "sync-request-7"
        assert sync_client.get("/sync/history").json()[0]["records_processed"] == 10
        detail = sync_client.get("/sync/history/7").json()
        assert detail["id"] == 7
        assert detail["summary"].startswith("Lidas 10")
        assert detail["warnings"] == []
        assert detail["messages"] == []
        assert sync_client.get("/sync/history/999").status_code == 404
        status_response = sync_client.get("/sync/status").json()
        assert status_response["final_status"] == "SUCESSO"
        assert status_response["records_processed"] == 10
        assert sync_client.get("/status").json() == status_response

        default_sync = sync_client.post("/sync")
        assert default_sync.status_code == 202
        assert fake.mode is SyncMode.INCREMENTAL

        period = sync_client.post(
            "/sync/run-period",
            json={"start_date": "2026-07-01", "end_date": "2026-07-22"},
            headers={"X-User": "jonathan"},
        )
        assert period.status_code == 202
        assert fake.mode is SyncMode.PERIOD
        assert fake.kwargs["user"] == "jonathan"


def test_sync_reprocess_accepts_period_file_or_sync_id(
    api_settings: ApplicationSettings,
) -> None:
    started_at = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    entry = SyncHistoryEntry(
        id=9,
        request_id="reprocess-9",
        mode=SyncMode.PERIOD,
        started_at=started_at,
        finished_at=None,
        duration_ms=None,
        status=SyncStatus.RUNNING,
        records_read=0,
        records_inserted=0,
        records_updated=0,
        records_ignored=0,
        errors=None,
        user="operador",
        origin=SyncOrigin.MANUAL,
    )

    class FakeReprocessor:
        async def period(self, start_date, end_date, *, user):
            self.call = ("period", start_date, end_date, user)
            return entry

        async def file(self, file_name, *, user):
            self.call = ("file", file_name, user)
            return entry

        async def sync_id(self, entry_id, *, user):
            self.call = ("sync_id", entry_id, user)
            return entry

    fake = FakeReprocessor()
    app = create_app(api_settings)
    app.dependency_overrides[get_sync_reprocessor] = lambda: fake
    with TestClient(app, headers={"X-API-Key": api_settings.api_key}) as sync_client:
        period = sync_client.post(
            "/sync/reprocess",
            json={"start_date": "2026-07-01", "end_date": "2026-07-07"},
        )
        assert period.status_code == 202
        assert fake.call[0] == "period"
        file_response = sync_client.post(
            "/sync/reprocess", json={"file": "active.xlsx"}
        )
        assert file_response.status_code == 202
        assert fake.call == ("file", "active.xlsx", "api-key")
        id_response = sync_client.post("/sync/reprocess", json={"sync_id": 7})
        assert id_response.status_code == 202
        assert fake.call == ("sync_id", 7, "api-key")
        invalid = sync_client.post(
            "/sync/reprocess",
            json={"sync_id": 7, "file": "active.xlsx"},
        )
        assert invalid.status_code == 422


def test_sync_conflict_returns_http_409(api_settings: ApplicationSettings) -> None:
    class BusyCoordinator:
        async def start(self, *args, **kwargs):
            raise SyncAlreadyRunningError()

    app = create_app(api_settings)
    app.dependency_overrides[get_sync_coordinator] = lambda: BusyCoordinator()
    with TestClient(app, headers={"X-API-Key": api_settings.api_key}) as sync_client:
        response = sync_client.post("/sync/run", json={"mode": "FULL"})
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "J\u00e1 existe uma sincroniza\u00e7\u00e3o em execu\u00e7\u00e3o."


def test_performance_filters_pagination_and_response_schema(
    client: TestClient,
    performance_service: MagicMock,
) -> None:
    performance_service.listar.return_value = [_record()]
    response = client.get(
        "/performance",
        params={
            "transportadora": "TRANS A",
            "uf_destino": "SP",
            "cidade_destino": "SAO PAULO",
            "prazo": "NO PRAZO",
            "situacao": "ENTREGUE",
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "limit": 25,
            "offset": 50,
            "order_by": "Saída",
            "descending": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["nota_fiscal"] == "NF-001"
    assert payload["saida"] == "2026-07-20"
    assert payload["flag_devolucao_nf"] is False
    assert len(payload) == 22
    performance_service.listar.assert_called_once_with(
        PerformanceQuery(
            transportadora="TRANS A",
            uf_destino="SP",
            cidade_destino="SAO PAULO",
            prazo="NO PRAZO",
            situacao="ENTREGUE",
            periodo_inicio=date(2026, 7, 1),
            periodo_fim=date(2026, 7, 31),
            limit=25,
            offset=50,
            order_by="Saída",
            descending=True,
        )
    )


def test_performance_by_invoice_and_not_found(
    client: TestClient,
    performance_service: MagicMock,
) -> None:
    performance_service.buscar_nf.return_value = [_record("NF 001")]
    response = client.get("/performance/NF%20001")

    assert response.status_code == 200
    assert response.json()[0]["nota_fiscal"] == "NF 001"
    performance_service.buscar_nf.assert_called_once_with("NF 001")

    performance_service.buscar_nf.return_value = []
    response = client.get("/performance/INEXISTENTE")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


def test_dashboard(client: TestClient, dashboard_service: MagicMock) -> None:
    dashboard_service.total_registros.return_value = 10
    dashboard_service.total_atrasadas.return_value = 2
    dashboard_service.total_em_aberto.return_value = 3
    dashboard_service.total_entregues.return_value = 4
    dashboard_service.total_devolvidas.return_value = 1
    dashboard_service.percentual_atraso.return_value = 20.0
    dashboard_service.percentual_entregues.return_value = 40.0
    dashboard_service.percentual_devolvidas.return_value = 10.0

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.json() == {
        "total_registros": 10,
        "total_atrasadas": 2,
        "total_em_aberto": 3,
        "total_entregues": 4,
        "total_devolvidas": 1,
        "percentual_atraso": 20.0,
        "percentual_entregues": 40.0,
        "percentual_devolvidas": 10.0,
    }


@pytest.mark.parametrize(
    ("path", "method_name"),
    [
        ("/dashboard/transportadoras", "transportadoras"),
        ("/dashboard/ufs", "ufs"),
        ("/dashboard/cidades", "cidades"),
    ],
)
def test_dashboard_categories(
    client: TestClient,
    dashboard_service: MagicMock,
    path: str,
    method_name: str,
) -> None:
    getattr(dashboard_service, method_name).return_value = (
        CategoryCount("SP", 3),
        CategoryCount("MG", 1),
    )

    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == [
        {"label": "SP", "count": 3},
        {"label": "MG", "count": 1},
    ]


def test_validation_errors_do_not_call_service(
    client: TestClient,
    performance_service: MagicMock,
) -> None:
    assert client.get("/performance", params={"limit": 0}).status_code == 422
    assert (
        client.get(
            "/performance", params={"periodo_inicio": "21/07/2026"}
        ).status_code
        == 422
    )
    performance_service.listar.assert_not_called()


def test_service_error_is_safe_http_503(
    client: TestClient,
    performance_service: MagicMock,
) -> None:
    performance_service.listar.side_effect = ServiceError("segredo interno")
    response = client.get("/performance")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "segredo" not in response.text
    assert "traceback" not in response.text.lower()


def test_invalid_query_cause_is_http_422(
    client: TestClient,
    performance_service: MagicMock,
) -> None:
    error = ServiceError("consulta")
    error.__cause__ = InvalidQueryError("ordenação inválida")
    performance_service.listar.side_effect = error

    response = client.get("/performance", params={"order_by": "invalida"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_QUERY"


def test_dashboard_error_is_safe_http_503(
    client: TestClient,
    dashboard_service: MagicMock,
) -> None:
    dashboard_service.total_registros.side_effect = DashboardError("interno")
    response = client.get("/dashboard")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_global_error_middleware_returns_request_id_without_internal_details(
    client: TestClient,
    performance_service: MagicMock,
) -> None:
    performance_service.listar.side_effect = RuntimeError("segredo-interno")
    response = client.get("/performance", headers={"X-Request-ID": "req-sprint-17"})
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "req-sprint-17"
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Erro interno do servidor",
            "request_id": "req-sprint-17",
        }
    }
    assert "segredo-interno" not in response.text


def test_default_dependency_graph_creates_empty_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "api.sqlite3"
    settings = ApplicationSettings(
        environment=AppEnvironment.TEST,
        api_key="test-api-key-123456789",
        allowed_origins=("http://localhost:5173",),
        database_path=database_path,
        version="test",
        build_date="test",
    )

    with TestClient(create_app(settings)) as real_client:
        response = real_client.get(
            "/performance", headers={"X-API-Key": settings.api_key}
        )

    assert response.status_code == 200
    assert response.json() == []
    assert database_path.exists()


def test_api_architectural_boundary() -> None:
    root = Path(__file__).parents[1] / "active_sync"
    api_root = root / "api"
    lower_layers = (
        root / "services",
        root / "repository",
        root / "persistence",
        root / "transformer",
    )
    forbidden_sql = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ")

    for path in api_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name != "dependencies.py":
            assert not any(fragment in text.upper() for fragment in forbidden_sql)
        if path.name == "dependencies.py":
            continue
        tree = ast.parse(text)
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not any(
            module.startswith(("active_sync.repository", "active_sync.persistence"))
            for module in imports
        )

    for directory in lower_layers:
        for path in directory.glob("*.py"):
            assert "active_sync.api" not in path.read_text(encoding="utf-8")
