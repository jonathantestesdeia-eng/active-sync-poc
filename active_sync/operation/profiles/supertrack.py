"""Perfil operacional amplo do SuperTrack."""

from __future__ import annotations

from datetime import date, datetime
import logging
import unicodedata
from typing import Any

import pandas as pd

from active_sync.config import ProcessingProfile
from active_sync.operation.models import SyncMode
from active_sync.persistence import (
    DatabaseManager,
    SUPERTRACK_COLUMNS,
    SUPERTRACK_KEY_COLUMNS,
    delete_supertrack_movements,
    merge_supertrack_movements,
)
from active_sync.transformer.normalization import (
    identifier_as_text,
    normalize_null,
    safe_date_series,
    safe_number_series,
    trim_text,
)
from active_sync.transformer.transforms import build_destinatario, build_transportadora

from .base import ProfileBatch, ProfilePersistResult


REQUIRED_COLUMNS = (
    "Transportador",
    "Série",
    "CTe",
    "Nota Fiscal",
    "Tipo",
    "Cancelamento",
    "Destinatário",
    "Remetente",
    "Cidade Origem",
    "Cidade Destino",
    "UF Destino",
    "Emissão",
    "Saída",
    "Previsão",
    "Entrega",
    "Observacao",
    "Valor Frete",
)
FALSE_CANCELLATION_VALUES = frozenset({"", "0", "false", "n", "nao", "não"})
TRUE_CANCELLATION_VALUES = frozenset(
    {"1", "true", "s", "sim", "cancelado", "cancelada"}
)


def _fold(value: Any) -> str:
    text = trim_text(value) or ""
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii").casefold()


def is_cancelled(value: Any) -> bool:
    """Reconhece somente data ou indicador explícito de cancelamento."""
    normalized = normalize_null(value)
    if normalized is None:
        return False
    if isinstance(normalized, (date, datetime, pd.Timestamp)):
        return True
    folded = _fold(normalized)
    if folded in FALSE_CANCELLATION_VALUES:
        return False
    if folded in TRUE_CANCELLATION_VALUES:
        return True
    parsed = pd.to_datetime(normalized, errors="coerce", format="mixed", dayfirst=True)
    return bool(pd.notna(parsed))


def _party_identifier(value: Any) -> str:
    text = trim_text(value) or ""
    return (identifier_as_text(text.split(" - ", 1)[0]) or text or "SEM-ID").strip()


def _required_identifier(value: Any, fallback: str) -> str:
    return identifier_as_text(value) or fallback


def _operational_situation(
    document_type: pd.Series,
    delivery: pd.Series,
) -> pd.Series:
    types = document_type.map(lambda value: (trim_text(value) or "").upper())
    delivered = safe_date_series(delivery).notna()
    result = pd.Series("EM ABERTO", index=document_type.index, dtype="object")
    result.loc[delivered] = "ENTREGUE"
    result.loc[types.str.contains("DEVOLU", regex=False)] = "DEVOLVIDA"
    return result


def build_supertrack_movements(raw: pd.DataFrame) -> ProfileBatch:
    """Preserva todos os movimentos não cancelados e deduplica a chave operacional."""
    missing = [name for name in REQUIRED_COLUMNS if name not in raw.columns]
    if missing:
        raise ValueError(f"Excel operacional sem colunas obrigatórias: {missing}.")

    cancelled = raw["Cancelamento"].map(is_cancelled)
    cancelled_rows = raw.loc[cancelled]
    cancelled_keys = tuple(
        (
            _party_identifier(row["Transportador"]),
            _required_identifier(row["Série"], "SEM-SERIE"),
            _required_identifier(row["CTe"], "SEM-CTE"),
            _required_identifier(row["Nota Fiscal"], "SEM-NF"),
        )
        for _, row in cancelled_rows.iterrows()
    )
    active = raw.loc[~cancelled].copy()
    result = pd.DataFrame(index=active.index)
    result["transportador_id"] = active["Transportador"].map(_party_identifier)
    result["serie_cte"] = active["Série"].map(
        lambda value: _required_identifier(value, "SEM-SERIE")
    )
    result["cte"] = active["CTe"].map(
        lambda value: _required_identifier(value, "SEM-CTE")
    )
    result["nota_fiscal"] = active["Nota Fiscal"].map(
        lambda value: _required_identifier(value, "SEM-NF")
    )
    result["chave_cte"] = active.get(
        "Chave CTe", pd.Series(None, index=active.index)
    ).map(identifier_as_text)
    result["serie_nf"] = active.get(
        "Série.1", pd.Series(None, index=active.index)
    ).map(identifier_as_text)
    result["pedido"] = active.get(
        "Pedido", pd.Series(None, index=active.index)
    ).map(identifier_as_text)
    result["tipo_cte"] = active["Tipo"].map(trim_text)
    result["transportadora"] = build_transportadora(active["Transportador"])
    result["remetente"] = build_destinatario(active["Remetente"])
    result["destinatario"] = build_destinatario(active["Destinatário"])
    result["cnpj_destinatario"] = active["Destinatário"].map(_party_identifier)
    result["cidade_origem"] = active["Cidade Origem"].map(trim_text)
    result["cidade_destino"] = active["Cidade Destino"].map(trim_text)
    result["uf_destino"] = active["UF Destino"].map(trim_text)
    for target, source in (
        ("emissao", "Emissão"),
        ("saida", "Saída"),
        ("previsao", "Previsão"),
        ("entrega", "Entrega"),
        ("data_atualizacao", "Data Inclusão"),
    ):
        values = active.get(source, pd.Series(None, index=active.index))
        result[target] = safe_date_series(values)
    result["situacao"] = _operational_situation(active["Tipo"], active["Entrega"])
    result["observacao"] = active["Observacao"].map(trim_text)
    result["valor_frete"] = safe_number_series(active["Valor Frete"])
    result = result.loc[:, list(SUPERTRACK_COLUMNS)]

    duplicated = result.duplicated(
        subset=list(SUPERTRACK_KEY_COLUMNS), keep="last"
    )
    duplicates_removed = int(duplicated.sum())
    result = result.loc[~duplicated].copy()
    return_types = result["tipo_cte"].fillna("").str.upper().str.contains(
        "DEVOLU", regex=False
    )
    per_invoice_ctes = result.groupby("nota_fiscal")["cte"].nunique()
    return ProfileBatch(
        frame=result,
        extracted=len(raw),
        removed=int(cancelled.sum()) + duplicates_removed,
        cancelled_removed=int(cancelled.sum()),
        duplicates_removed=duplicates_removed,
        movements_preserved=len(result),
        returns_preserved=int(return_types.sum()),
        unique_invoices=int(result["nota_fiscal"].nunique()),
        unique_ctes=int(result["cte"].nunique()),
        invoices_with_multiple_ctes=int((per_invoice_ctes > 1).sum()),
        cancelled_keys=cancelled_keys,
    )


class SuperTrackProfile:
    name = ProcessingProfile.SUPERTRACK

    def process(
        self,
        raw: pd.DataFrame,
        *,
        client_register: pd.DataFrame | None,
        logger: logging.Logger,
    ) -> ProfileBatch:
        del client_register
        batch = build_supertrack_movements(raw)
        logger.info(
            "supertrack_profile_processed",
            extra={
                "profile": self.name.value,
                "total_extraido": batch.extracted,
                "total_cancelados_removidos": batch.cancelled_removed,
                "total_duplicidades_removidas": batch.duplicates_removed,
                "total_movimentos_preservados": batch.movements_preserved,
                "total_devolucoes_preservadas": batch.returns_preserved,
                "total_nfs_unicas": batch.unique_invoices,
                "total_ctes_unicos": batch.unique_ctes,
                "total_nfs_com_multiplos_ctes": batch.invoices_with_multiple_ctes,
            },
        )
        return batch

    def persist(
        self,
        batch: ProfileBatch,
        database: DatabaseManager,
        *,
        request_id: str,
    ) -> ProfilePersistResult:
        removed = delete_supertrack_movements(database, batch.cancelled_keys)
        result = merge_supertrack_movements(
            batch.frame, database, request_id=request_id
        )
        if removed:
            logging.getLogger(__name__).info(
                "supertrack_cancelled_movements_deleted",
                extra={"profile": self.name.value, "total_removed": removed},
            )
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
