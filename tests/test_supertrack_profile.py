from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from active_sync.api import create_app
from active_sync.config import AppEnvironment, ApplicationSettings
from active_sync.operation.models import SyncMode
from active_sync.operation.profiles import (
    PERFORMANCE_RECONCILIATION_RULES,
    SuperTrackProfile,
    build_supertrack_movements,
    is_cancelled,
)
from active_sync.persistence import DatabaseManager, MigrationManager
from active_sync.repository import SuperTrackRepository
from active_sync.transformer import apply_reconciliation_rules


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Transportador": "02561910000100 - ATIVA",
        "Série": "1",
        "CTe": "100",
        "Nota Fiscal": "12345",
        "Tipo": "ENTREGA NORMAL",
        "Cancelamento": None,
        "Destinatário": "11206099000107 - CLIENTE",
        "Remetente": "99887766000100 - SUPERMED",
        "Cidade Origem": "SAO PAULO",
        "Cidade Destino": "ITATIAIA",
        "UF Destino": "RJ",
        "Emissão": "07/07/2026",
        "Saída": "08/07/2026",
        "Previsão": "10/07/2026",
        "Entrega": None,
        "Observacao": None,
        "Valor Frete": "10,50",
        "Chave CTe": "352607",
        "Série.1": "2",
        "Pedido": "P-1",
        "Data Inclusão": "08/07/2026",
        "Tomador": "99887766000100 - SUPERMED",
        "Fatura": None,
        "Aprovação Financeira": None,
        "Operação Fiscal": None,
        "Redespacho": None,
    }
    row.update(changes)
    return row


def test_cancellation_is_explicit_and_does_not_inspect_observation() -> None:
    for value in (None, "", "0", "não", "texto inesperado"):
        assert is_cancelled(value) is False
    for value in (" SIM ", "cancelado", "22/07/2026", pd.Timestamp("2026-07-22")):
        assert is_cancelled(value) is True


def test_supertrack_preserves_all_types_and_only_real_duplicates() -> None:
    raw = pd.DataFrame(
        [
            _row(),
            _row(CTe="200", Tipo="REENTREGA"),
            _row(
                CTe="28340",
                **{
                    "Nota Fiscal": "1015048",
                    "Tipo": "DEVOLUCAO",
                    "Destinatário": "11206099000107 - SUPERMED",
                    "Observacao": "DEVOLUCAO TOTAL POR DUPLICIDADE DE PEDIDO",
                },
            ),
            _row(CTe="300", Tipo="COMPLEMENTAR"),
            _row(CTe="300", Tipo="COMPLEMENTAR"),
            _row(CTe="400", Cancelamento="22/07/2026"),
            _row(Transportador="99999999000100 - OUTRA"),
        ]
    )

    batch = build_supertrack_movements(raw)

    assert set(batch.frame["tipo_cte"]) == {
        "ENTREGA NORMAL",
        "REENTREGA",
        "DEVOLUCAO",
        "COMPLEMENTAR",
    }
    assert len(batch.frame) == 5
    assert batch.cancelled_removed == 1
    assert batch.duplicates_removed == 1
    assert batch.returns_preserved == 1
    devolucao = batch.frame.loc[batch.frame["nota_fiscal"] == "1015048"].iloc[0]
    assert devolucao["cte"] == "28340"
    assert devolucao["destinatario"] == "SUPERMED"
    assert devolucao["situacao"] == "DEVOLVIDA"


def test_performance_profile_keeps_previous_reconciliation_behavior() -> None:
    raw = pd.DataFrame(
        [
            _row(),
            _row(CTe="200", Tipo="REENTREGA"),
            _row(CTe="28340", Tipo="DEVOLUCAO"),
        ]
    )
    result = apply_reconciliation_rules(
        raw, PERFORMANCE_RECONCILIATION_RULES, logging.getLogger("test")
    )
    assert set(result["Tipo"]) == {"ENTREGA NORMAL", "REENTREGA"}


def test_persistence_preserves_multiple_ctes_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "supertrack.sqlite3"
    profile = SuperTrackProfile()
    batch = build_supertrack_movements(
        pd.DataFrame([_row(), _row(CTe="200", Tipo="DEVOLUCAO")])
    )
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        first = profile.persist(batch, database, request_id="run-1")
        second = profile.persist(batch, database, request_id="run-2")
        records = SuperTrackRepository(database).buscar_por_nf("12345")

    assert (first.inserted, first.updated, first.ignored) == (2, 0, 0)
    assert (second.inserted, second.updated, second.ignored) == (0, 0, 2)
    assert [record.cte for record in records] == ["100", "200"]


def test_full_preserves_movements_absent_from_the_current_partial_export(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "full.sqlite3"
    profile = SuperTrackProfile()
    initial = build_supertrack_movements(
        pd.DataFrame([_row(), _row(CTe="200")])
    )
    current = build_supertrack_movements(pd.DataFrame([_row(CTe="200")]))
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        profile.persist(initial, database, request_id="old")
        profile.persist(current, database, request_id="full-new")
        removed = profile.finalize(
            database, mode=SyncMode.FULL, request_id="full-new"
        )
        records = SuperTrackRepository(database).buscar_por_nf("12345")

    assert removed == 0
    assert [record.cte for record in records] == ["100", "200"]


def test_overlapping_import_updates_and_preserves_historical_movements(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "overlap.sqlite3"
    profile = SuperTrackProfile()
    first_window = build_supertrack_movements(
        pd.DataFrame(
            [
                _row(CTe="100", **{"Nota Fiscal": "NF-01"}),
                _row(
                    CTe="700",
                    **{
                        "Nota Fiscal": "NF-07",
                        "Previsão": "10/07/2026",
                    },
                ),
            ]
        )
    )
    overlapping_window = build_supertrack_movements(
        pd.DataFrame(
            [
                _row(
                    CTe="700",
                    **{
                        "Nota Fiscal": "NF-07",
                        "Previsão": "12/07/2026",
                        "Entrega": "11/07/2026",
                    },
                ),
                _row(CTe="800", **{"Nota Fiscal": "NF-08"}),
            ]
        )
    )
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        initial = profile.persist(first_window, database, request_id="window-01-07")
        before = database.execute(
            '''SELECT first_seen_at, created_at FROM supertrack_movements
            WHERE nota_fiscal = 'NF-07' '''
        ).fetchone()
        overlap = profile.persist(
            overlapping_window, database, request_id="window-07-08"
        )
        repeated = profile.persist(
            overlapping_window, database, request_id="window-07-08-repeat"
        )
        rows = database.execute(
            '''SELECT nota_fiscal, cte, previsao, entrega, situacao,
                      first_seen_at, last_seen_at, last_sync_id,
                      updated_at, created_at
            FROM supertrack_movements ORDER BY nota_fiscal'''
        ).fetchall()

    assert (initial.inserted, initial.updated) == (2, 0)
    assert (overlap.inserted, overlap.updated, overlap.ignored) == (1, 1, 0)
    assert (repeated.inserted, repeated.updated, repeated.ignored) == (0, 0, 2)
    assert [(row["nota_fiscal"], row["cte"]) for row in rows] == [
        ("NF-01", "100"),
        ("NF-07", "700"),
        ("NF-08", "800"),
    ]
    updated = rows[1]
    assert updated["previsao"] == "2026-07-12"
    assert updated["entrega"] == "2026-07-11"
    assert updated["situacao"] == "ENTREGUE"
    assert updated["first_seen_at"] == before["first_seen_at"]
    assert updated["created_at"] == before["created_at"]
    assert updated["last_sync_id"] == "window-07-08-repeat"
    assert updated["last_seen_at"]
    assert updated["updated_at"]


def test_bulk_upsert_handles_more_than_one_sqlite_parameter_batch(
    tmp_path: Path,
) -> None:
    frame = pd.DataFrame(
        [
            _row(CTe=str(100000 + index), **{"Nota Fiscal": f"NF-{index}"})
            for index in range(450)
        ]
    )
    batch = build_supertrack_movements(frame)
    with DatabaseManager(tmp_path / "bulk.sqlite3") as database:
        MigrationManager(database).migrate()
        first = SuperTrackProfile().persist(batch, database, request_id="bulk-1")
        repeated = SuperTrackProfile().persist(
            batch, database, request_id="bulk-2"
        )
        total = database.execute(
            "SELECT COUNT(*) FROM supertrack_movements"
        ).fetchone()[0]

    assert (first.inserted, first.updated, first.ignored) == (450, 0, 0)
    assert (repeated.inserted, repeated.updated, repeated.ignored) == (0, 0, 450)
    assert total == 450


def test_incremental_cancellation_removes_only_the_exact_movement(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cancel.sqlite3"
    profile = SuperTrackProfile()
    initial = build_supertrack_movements(
        pd.DataFrame([_row(), _row(CTe="200")])
    )
    cancellation = build_supertrack_movements(
        pd.DataFrame([_row(Cancelamento="23/07/2026")])
    )
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        profile.persist(initial, database, request_id="initial")
        profile.persist(cancellation, database, request_id="incremental")
        records = SuperTrackRepository(database).buscar_por_nf("12345")

    assert [record.cte for record in records] == ["200"]


def test_tracking_api_returns_collection_and_404(tmp_path: Path) -> None:
    database_path = tmp_path / "api.sqlite3"
    settings = ApplicationSettings(
        environment=AppEnvironment.TEST,
        api_key="test-api-key-123456789",
        allowed_origins=("http://localhost:5173",),
        database_path=database_path,
        version="test",
        build_date="test",
    )
    batch = build_supertrack_movements(
        pd.DataFrame(
            [
                _row(
                    CTe="28340",
                    **{
                        "Nota Fiscal": "1015048",
                        "Tipo": "DEVOLUCAO",
                        "Destinatário": "11206099000107 - SUPERMED",
                        "Observacao": "DEVOLUCAO TOTAL POR DUPLICIDADE DE PEDIDO",
                    },
                ),
                _row(CTe="30000", **{"Nota Fiscal": "1015048"}),
            ]
        )
    )
    with DatabaseManager(database_path) as database:
        MigrationManager(database).migrate()
        SuperTrackProfile().persist(batch, database, request_id="api-fixture")

    with TestClient(
        create_app(settings),
        headers={"X-API-Key": settings.api_key},
    ) as client:
        response = client.get("/tracking/1015048")
        missing = client.get("/tracking/999999")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert {item["cte"] for item in payload["movimentos"]} == {"28340", "30000"}
    devolucao = next(item for item in payload["movimentos"] if item["cte"] == "28340")
    assert devolucao["tipoCte"] == "DEVOLUCAO"
    assert devolucao["destinatario"] == "SUPERMED"
    assert missing.status_code == 404
