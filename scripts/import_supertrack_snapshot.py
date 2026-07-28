"""Reconstrói a visão operacional a partir de um Excel bruto já baixado."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from active_sync.excel_reader import read_excel_dataframe
from active_sync.operation.models import SyncMode
from active_sync.operation.profiles import SuperTrackProfile
from active_sync.persistence import DatabaseManager, MigrationManager


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("excel", type=Path)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    request_id = f"snapshot-{uuid4()}"
    raw, _, _ = read_excel_dataframe(args.excel)
    profile = SuperTrackProfile()
    import logging

    batch = profile.process(
        raw, client_register=None, logger=logging.getLogger(__name__)
    )
    with DatabaseManager(args.database) as database:
        MigrationManager(database).migrate()
        persisted = profile.persist(batch, database, request_id=request_id)
        removed = profile.finalize(
            database,
            mode=SyncMode.FULL if args.full else SyncMode.PERIOD,
            request_id=request_id,
        )
    print(
        " ".join(
            (
                f"lidos={batch.extracted}",
                f"preservados={batch.movements_preserved}",
                f"cancelados={batch.cancelled_removed}",
                f"duplicados={batch.duplicates_removed}",
                f"devolucoes={batch.returns_preserved}",
                f"inseridos={persisted.inserted}",
                f"atualizados={persisted.updated}",
                f"ignorados={persisted.ignored}",
                f"removidos_por_ausencia={removed}",
            )
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
