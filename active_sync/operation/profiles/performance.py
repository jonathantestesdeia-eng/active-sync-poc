"""Perfil que preserva integralmente as regras homologadas de Performance."""

from __future__ import annotations

import logging

import pandas as pd

from active_sync.config import ProcessingProfile
from active_sync.operation.models import SyncMode
from active_sync.persistence import DatabaseManager, merge_dataframe
from active_sync.transformer import (
    ReconciliationRules,
    apply_reconciliation_rules,
    transform_dataframe,
)

from .base import ProfileBatch, ProfilePersistResult


PERFORMANCE_RECONCILIATION_RULES = ReconciliationRules(
    allowed_document_types=frozenset({"entrega normal", "reentrega"}),
    require_departure=True,
    exclude_recipient_equal_payer=True,
    require_financial_approval_for_invoiced=True,
)


class PerformanceProfile:
    name = ProcessingProfile.PERFORMANCE

    def process(
        self,
        raw: pd.DataFrame,
        *,
        client_register: pd.DataFrame | None,
        logger: logging.Logger,
    ) -> ProfileBatch:
        reconciled = apply_reconciliation_rules(
            raw, PERFORMANCE_RECONCILIATION_RULES, logger
        )
        transformed = transform_dataframe(
            reconciled,
            logger=logger,
            client_register=client_register,
        )
        return ProfileBatch(
            frame=transformed,
            extracted=len(raw),
            removed=len(raw) - len(reconciled),
            cancelled_removed=0,
            duplicates_removed=0,
            movements_preserved=len(transformed),
            returns_preserved=int(
                transformed["Flag Devolução NF"].sum()
            ),
            unique_invoices=int(transformed["Nota Fiscal"].nunique()),
            unique_ctes=0,
            invoices_with_multiple_ctes=0,
        )

    def persist(
        self,
        batch: ProfileBatch,
        database: DatabaseManager,
        *,
        request_id: str,
    ) -> ProfilePersistResult:
        del request_id
        result = merge_dataframe(batch.frame, database)
        return ProfilePersistResult(result.inserted, result.updated, result.ignored)

    def finalize(
        self,
        database: DatabaseManager,
        *,
        mode: SyncMode,
        request_id: str,
    ) -> int:
        del database, mode, request_id
        return 0
