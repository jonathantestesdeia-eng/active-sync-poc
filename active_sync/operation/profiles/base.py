"""Contratos dos perfis de processamento."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Protocol

import pandas as pd

from active_sync.config import ProcessingProfile
from active_sync.operation.models import SyncMode
from active_sync.persistence import DatabaseManager


@dataclass(frozen=True, slots=True)
class ProfileBatch:
    frame: pd.DataFrame
    extracted: int
    removed: int
    cancelled_removed: int
    duplicates_removed: int
    movements_preserved: int
    returns_preserved: int
    unique_invoices: int
    unique_ctes: int
    invoices_with_multiple_ctes: int
    cancelled_keys: tuple[tuple[str, str, str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ProfilePersistResult:
    inserted: int
    updated: int
    ignored: int


class ProcessingStrategy(Protocol):
    name: ProcessingProfile

    def process(
        self,
        raw: pd.DataFrame,
        *,
        client_register: pd.DataFrame | None,
        logger: logging.Logger,
    ) -> ProfileBatch: ...

    def persist(
        self,
        batch: ProfileBatch,
        database: DatabaseManager,
        *,
        request_id: str,
    ) -> ProfilePersistResult: ...

    def finalize(
        self,
        database: DatabaseManager,
        *,
        mode: SyncMode,
        request_id: str,
    ) -> int: ...
