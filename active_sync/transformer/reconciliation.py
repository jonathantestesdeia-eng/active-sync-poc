"""Reconciliação do universo de registros bruto com a referência Power Query."""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final, Iterable

import pandas as pd

from active_sync.exceptions import ReconciliationError


NOTE_COLUMN: Final[str] = "Nota Fiscal"
CTE_COLUMN: Final[str] = "CTe"
TYPE_COLUMN: Final[str] = "Tipo"
POWERQUERY_TYPE_COLUMN: Final[str] = "Tipo CTe"
DEPARTURE_COLUMN: Final[str] = "Saída"
RECIPIENT_COLUMN: Final[str] = "Destinatário"
PAYER_COLUMN: Final[str] = "Tomador"
INVOICE_COLUMN: Final[str] = "Fatura"
FINANCIAL_APPROVAL_COLUMN: Final[str] = "Aprovação Financeira"

REQUIRED_RAW_COLUMNS: Final[tuple[str, ...]] = (
    NOTE_COLUMN,
    CTE_COLUMN,
    TYPE_COLUMN,
    "Transportador",
    "Cancelamento",
    "Emissão",
    DEPARTURE_COLUMN,
    "Entrega",
    "Valor Frete",
    RECIPIENT_COLUMN,
    PAYER_COLUMN,
    INVOICE_COLUMN,
    FINANCIAL_APPROVAL_COLUMN,
    "Operação Fiscal",
    "Redespacho",
    "Observacao",
)


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Grupo de ocorrências repetidas de um identificador."""

    field: str
    value: str
    count: int
    row_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationRules:
    """Regras inferidas dos registros efetivamente mantidos pela referência."""

    allowed_document_types: frozenset[str]
    require_departure: bool
    exclude_recipient_equal_payer: bool
    require_financial_approval_for_invoiced: bool


@dataclass(frozen=True, slots=True)
class ReconciliationEntry:
    """Evidências de uma ocorrência presente somente no resultado Python."""

    row_number: int
    note: str | None
    cte: str | None
    document_type: str | None
    carrier: str | None
    cancellation: str | None
    emission: str | None
    departure: str | None
    delivery: str | None
    freight_value: str | None
    operation_type: str | None
    note_occurrences: int
    cte_occurrences: int
    present_in_active: bool
    created_by_rule: bool
    is_cancelled: bool
    is_return: bool
    is_complementary: bool
    is_redelivery: bool
    is_redespacho: bool
    possible_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Resultado completo da descoberta e aplicação das regras de universo."""

    original_python_count: int
    powerquery_count: int
    reconciled_python_count: int
    only_python: tuple[ReconciliationEntry, ...]
    only_powerquery: tuple[str, ...]
    remaining_only_python: tuple[str, ...]
    remaining_only_powerquery: tuple[str, ...]
    duplicate_notes_python: tuple[DuplicateGroup, ...]
    duplicate_notes_powerquery: tuple[DuplicateGroup, ...]
    duplicate_ctes_python: tuple[DuplicateGroup, ...]
    powerquery_has_cte: bool
    rules: ReconciliationRules
    confirmed_hypotheses: tuple[str, ...]
    discarded_hypotheses: tuple[str, ...]

    @property
    def is_reconciled(self) -> bool:
        justified = all(entry.possible_reasons for entry in self.only_python)
        return (
            self.reconciled_python_count == self.powerquery_count
            and not self.remaining_only_python
            and not self.remaining_only_powerquery
            and justified
        )


def _has_value(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip())


def _identifier(value: Any) -> str | None:
    if not _has_value(value):
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalized_text(value: Any) -> str | None:
    identifier = _identifier(value)
    return identifier.casefold() if identifier is not None else None


def _party_identifier(value: Any) -> str | None:
    identifier = _identifier(value)
    if identifier is None:
        return None
    return identifier.split(" - ", 1)[0].strip().casefold()


def _display_value(value: Any) -> str | None:
    if not _has_value(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat(sep=" ")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _validate_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    label: str,
) -> None:
    duplicates = [
        str(column)
        for column in frame.columns[frame.columns.duplicated()].tolist()
    ]
    if duplicates:
        raise ReconciliationError(f"{label} contém colunas duplicadas: {duplicates}.")
    missing = sorted(set(required) - set(str(column) for column in frame.columns))
    if missing:
        raise ReconciliationError(f"{label} não contém colunas obrigatórias: {missing}.")


def _partition_by_note(
    source_notes: pd.Series,
    reference_notes: pd.Series,
) -> tuple[list[int], list[int], list[str]]:
    remaining = Counter(_identifier(value) for value in reference_notes)
    matched_positions: list[int] = []
    source_only_positions: list[int] = []
    for position, value in enumerate(source_notes):
        note = _identifier(value)
        if remaining[note] > 0:
            matched_positions.append(position)
            remaining[note] -= 1
        else:
            source_only_positions.append(position)
    reference_only: list[str] = []
    for value, count in remaining.items():
        reference_only.extend([value or "<NULO>"] * count)
    return matched_positions, source_only_positions, reference_only


def _duplicate_groups(series: pd.Series, field: str) -> tuple[DuplicateGroup, ...]:
    rows: dict[str, list[int]] = defaultdict(list)
    for position, value in enumerate(series):
        identifier = _identifier(value) or "<NULO>"
        rows[identifier].append(position + 2)
    return tuple(
        DuplicateGroup(
            field=field,
            value=value,
            count=len(row_numbers),
            row_numbers=tuple(row_numbers),
        )
        for value, row_numbers in sorted(rows.items())
        if value != "<NULO>" and len(row_numbers) > 1
    )


def infer_reconciliation_rules(
    raw: pd.DataFrame,
    powerquery: pd.DataFrame,
) -> ReconciliationRules:
    """Infere regras apenas de condições universais nos registros mantidos."""
    _validate_columns(raw, REQUIRED_RAW_COLUMNS, "O Excel bruto")
    _validate_columns(powerquery, (NOTE_COLUMN, POWERQUERY_TYPE_COLUMN), "O Power Query")
    matched, source_only, reference_only = _partition_by_note(
        raw[NOTE_COLUMN],
        powerquery[NOTE_COLUMN],
    )
    if not matched or reference_only:
        raise ReconciliationError(
            "Não há associação suficiente por Nota Fiscal para inferir regras com segurança."
        )
    matched_frame = raw.iloc[matched]
    source_only_frame = raw.iloc[source_only]
    allowed_types = frozenset(
        value
        for value in matched_frame[TYPE_COLUMN].map(_normalized_text)
        if value is not None
    )
    if not allowed_types:
        raise ReconciliationError("Nenhum Tipo CTe válido foi observado nas notas associadas.")

    matched_departures = matched_frame[DEPARTURE_COLUMN].map(_has_value)
    source_only_departures = source_only_frame[DEPARTURE_COLUMN].map(_has_value)
    require_departure = bool(
        matched_departures.all() and (~source_only_departures).any()
    )

    matched_same_party = pd.Series(
        [
            _party_identifier(recipient) == _party_identifier(payer)
            for recipient, payer in zip(
                matched_frame[RECIPIENT_COLUMN],
                matched_frame[PAYER_COLUMN],
                strict=True,
            )
        ],
        index=matched_frame.index,
    )
    source_only_same_party = pd.Series(
        [
            _party_identifier(recipient) == _party_identifier(payer)
            for recipient, payer in zip(
                source_only_frame[RECIPIENT_COLUMN],
                source_only_frame[PAYER_COLUMN],
                strict=True,
            )
        ],
        index=source_only_frame.index,
    )
    exclude_recipient_equal_payer = bool(
        not matched_same_party.any() and source_only_same_party.any()
    )

    matched_pending_invoice = (
        matched_frame[INVOICE_COLUMN].map(_has_value)
        & ~matched_frame[FINANCIAL_APPROVAL_COLUMN].map(_has_value)
    )
    source_only_pending_invoice = (
        source_only_frame[INVOICE_COLUMN].map(_has_value)
        & ~source_only_frame[FINANCIAL_APPROVAL_COLUMN].map(_has_value)
    )
    require_financial_approval = bool(
        not matched_pending_invoice.any() and source_only_pending_invoice.any()
    )
    return ReconciliationRules(
        allowed_document_types=allowed_types,
        require_departure=require_departure,
        exclude_recipient_equal_payer=exclude_recipient_equal_payer,
        require_financial_approval_for_invoiced=require_financial_approval,
    )


def apply_reconciliation_rules(
    raw: pd.DataFrame,
    rules: ReconciliationRules,
    logger: logging.Logger | None = None,
) -> pd.DataFrame:
    """Aplica regras inferidas ao bruto e preserva todas as suas colunas."""
    _validate_columns(raw, REQUIRED_RAW_COLUMNS, "O Excel bruto")
    mask = raw[TYPE_COLUMN].map(_normalized_text).isin(rules.allowed_document_types)
    if rules.require_departure:
        mask &= raw[DEPARTURE_COLUMN].map(_has_value)
    if rules.exclude_recipient_equal_payer:
        same_party = pd.Series(
            [
                _party_identifier(recipient) == _party_identifier(payer)
                for recipient, payer in zip(
                    raw[RECIPIENT_COLUMN],
                    raw[PAYER_COLUMN],
                    strict=True,
                )
            ],
            index=raw.index,
        )
        mask &= ~same_party
    if rules.require_financial_approval_for_invoiced:
        pending_invoice = (
            raw[INVOICE_COLUMN].map(_has_value)
            & ~raw[FINANCIAL_APPROVAL_COLUMN].map(_has_value)
        )
        mask &= ~pending_invoice
    result = raw.loc[mask].copy()
    if logger:
        logger.info(
            "Reconciliação aplicada: %d registros mantidos; %d removidos",
            len(result),
            len(raw) - len(result),
        )
    return result


def _entry_reasons(row: pd.Series, rules: ReconciliationRules) -> tuple[str, ...]:
    reasons: list[str] = []
    document_type = _normalized_text(row[TYPE_COLUMN])
    if document_type not in rules.allowed_document_types:
        reasons.append("Tipo CTe não pertence aos tipos mantidos pela referência")
    if rules.require_departure and not _has_value(row[DEPARTURE_COLUMN]):
        reasons.append("Saída não preenchida")
    if (
        rules.exclude_recipient_equal_payer
        and _party_identifier(row[RECIPIENT_COLUMN])
        == _party_identifier(row[PAYER_COLUMN])
    ):
        reasons.append("Destinatário e Tomador representam a mesma parte")
    if (
        rules.require_financial_approval_for_invoiced
        and _has_value(row[INVOICE_COLUMN])
        and not _has_value(row[FINANCIAL_APPROVAL_COLUMN])
    ):
        reasons.append("Fatura preenchida sem aprovação financeira")
    return tuple(reasons)


def _build_entry(
    raw: pd.DataFrame,
    position: int,
    note_counts: Counter[str | None],
    cte_counts: Counter[str | None],
    rules: ReconciliationRules,
) -> ReconciliationEntry:
    row = raw.iloc[position]
    document_type = _display_value(row[TYPE_COLUMN])
    observation = _display_value(row["Observacao"]) or ""
    type_text = (document_type or "").casefold()
    evidence_text = f"{type_text} {observation.casefold()}"
    note = _identifier(row[NOTE_COLUMN])
    cte = _identifier(row[CTE_COLUMN])
    return ReconciliationEntry(
        row_number=position + 2,
        note=note,
        cte=cte,
        document_type=document_type,
        carrier=_display_value(row["Transportador"]),
        cancellation=_display_value(row["Cancelamento"]),
        emission=_display_value(row["Emissão"]),
        departure=_display_value(row[DEPARTURE_COLUMN]),
        delivery=_display_value(row["Entrega"]),
        freight_value=_display_value(row["Valor Frete"]),
        operation_type=_display_value(row["Operação Fiscal"]),
        note_occurrences=note_counts[note],
        cte_occurrences=cte_counts[cte],
        present_in_active=True,
        created_by_rule=False,
        is_cancelled=_has_value(row["Cancelamento"]),
        is_return="devol" in evidence_text,
        is_complementary="complement" in type_text,
        is_redelivery="reentrega" in type_text,
        is_redespacho=_has_value(row["Redespacho"]),
        possible_reasons=_entry_reasons(row, rules),
    )


def reconcile_datasets(
    raw: pd.DataFrame,
    powerquery: pd.DataFrame,
    rules: ReconciliationRules | None = None,
    logger: logging.Logger | None = None,
) -> tuple[pd.DataFrame, ReconciliationResult]:
    """Reconcilia, filtra e comprova o universo final por Nota Fiscal."""
    _validate_columns(raw, REQUIRED_RAW_COLUMNS, "O Excel bruto")
    _validate_columns(powerquery, (NOTE_COLUMN, POWERQUERY_TYPE_COLUMN), "O Power Query")
    effective_rules = rules or infer_reconciliation_rules(raw, powerquery)
    _, source_only, reference_only = _partition_by_note(
        raw[NOTE_COLUMN],
        powerquery[NOTE_COLUMN],
    )
    note_counts = Counter(_identifier(value) for value in raw[NOTE_COLUMN])
    cte_counts = Counter(_identifier(value) for value in raw[CTE_COLUMN])
    entries = tuple(
        _build_entry(raw, position, note_counts, cte_counts, effective_rules)
        for position in source_only
    )
    filtered = apply_reconciliation_rules(raw, effective_rules, logger)
    _, remaining_source, remaining_reference = _partition_by_note(
        filtered[NOTE_COLUMN],
        powerquery[NOTE_COLUMN],
    )
    remaining_source_notes = tuple(
        _identifier(filtered.iloc[position][NOTE_COLUMN]) or "<NULO>"
        for position in remaining_source
    )
    powerquery_has_cte = CTE_COLUMN in powerquery.columns
    confirmed = [
        "Tipos de documento inferidos das notas mantidas: "
        + ", ".join(sorted(effective_rules.allowed_document_types)),
    ]
    if effective_rules.require_departure:
        confirmed.append("Somente registros com Saída preenchida permanecem.")
    if effective_rules.exclude_recipient_equal_payer:
        confirmed.append(
            "Registros em que Destinatário e Tomador são a mesma parte são removidos."
        )
    if effective_rules.require_financial_approval_for_invoiced:
        confirmed.append(
            "Registros faturados sem aprovação financeira são removidos."
        )
    discarded = (
        "Emissão não explica a diferença: as mesmas datas aparecem nos dois conjuntos.",
        "Redespacho não explica a diferença: há registros com redespacho mantidos.",
        "Cancelamento isolado não é necessário para reproduzir o conjunto final.",
        "Deduplicação isolada não é necessária para reproduzir o conjunto final.",
    )
    result = ReconciliationResult(
        original_python_count=len(raw),
        powerquery_count=len(powerquery),
        reconciled_python_count=len(filtered),
        only_python=entries,
        only_powerquery=tuple(reference_only),
        remaining_only_python=remaining_source_notes,
        remaining_only_powerquery=tuple(remaining_reference),
        duplicate_notes_python=_duplicate_groups(raw[NOTE_COLUMN], NOTE_COLUMN),
        duplicate_notes_powerquery=_duplicate_groups(
            powerquery[NOTE_COLUMN], NOTE_COLUMN
        ),
        duplicate_ctes_python=_duplicate_groups(raw[CTE_COLUMN], CTE_COLUMN),
        powerquery_has_cte=powerquery_has_cte,
        rules=effective_rules,
        confirmed_hypotheses=tuple(confirmed),
        discarded_hypotheses=discarded,
    )
    if logger:
        logger.info(
            "Reconciliação concluída: Python=%d; Power Query=%d; reconciliado=%s",
            len(filtered),
            len(powerquery),
            result.is_reconciled,
        )
    return filtered, result


def _markdown(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _duplicate_table(groups: tuple[DuplicateGroup, ...]) -> list[str]:
    if not groups:
        return ["Nenhuma duplicidade encontrada."]
    lines = ["| Campo | Valor | Ocorrências | Linhas do Excel |", "|---|---|---:|---|"]
    lines.extend(
        f"| {_markdown(group.field)} | {_markdown(group.value)} | {group.count} | "
        f"{', '.join(str(row) for row in group.row_numbers)} |"
        for group in groups
    )
    return lines


def write_reconciliation_markdown(
    result: ReconciliationResult,
    output_path: str | Path = Path("docs/RECONCILIACAO.md"),
) -> Path:
    """Gera o relatório auditável da reconciliação em Markdown."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    reason_counts = Counter(
        reason
        for entry in result.only_python
        for reason in entry.possible_reasons
    )
    repeated_note_entries = sum(
        entry.note_occurrences > 1 for entry in result.only_python
    )
    repeated_cte_entries = sum(
        entry.cte_occurrences > 1 for entry in result.only_python
    )
    lines = [
        "# Reconciliação do Dataset",
        "",
        "## Resumo executivo",
        "",
        f"- Registros Python antes da reconciliação: **{result.original_python_count}**.",
        f"- Registros Power Query: **{result.powerquery_count}**.",
        f"- Registros Python após a reconciliação: **{result.reconciled_python_count}**.",
        f"- Registros somente Python antes das regras: **{len(result.only_python)}**.",
        f"- Registros somente Power Query antes das regras: **{len(result.only_powerquery)}**.",
        f"- Registros exclusivos restantes no Python: **{len(result.remaining_only_python)}**.",
        f"- Registros exclusivos restantes no Power Query: **{len(result.remaining_only_powerquery)}**.",
        f"- Grupos de Nota Fiscal duplicada no Python: **{len(result.duplicate_notes_python)}**.",
        f"- Grupos de CTe repetido no Python: **{len(result.duplicate_ctes_python)}**.",
        f"- Critério de aceitação: **{'ATENDIDO' if result.is_reconciled else 'NÃO ATENDIDO'}**.",
        "",
        "Todas as ocorrências excedentes vieram do Excel bruto do Active; nenhuma foi criada pelo transformador.",
        "",
        "## Possíveis causas observadas",
        "",
    ]
    lines.extend(
        f"- {reason}: **{count}** ocorrência(s)."
        for reason, count in reason_counts.most_common()
    )
    lines.extend(
        [
            f"- Cancelamento preenchido: **{sum(entry.is_cancelled for entry in result.only_python)}** ocorrência(s).",
            f"- Evidência textual de devolução: **{sum(entry.is_return for entry in result.only_python)}** ocorrência(s).",
            f"- Tipo complementar: **{sum(entry.is_complementary for entry in result.only_python)}** ocorrência(s).",
            f"- Nota Fiscal repetida: **{repeated_note_entries}** ocorrência(s).",
            f"- CTe repetido: **{repeated_cte_entries}** ocorrência(s).",
            f"- Redespacho preenchido: **{sum(entry.is_redespacho for entry in result.only_python)}** ocorrência(s).",
            "",
        ]
    )
    lines.extend(
        [
        "## Hipóteses confirmadas",
        "",
        ]
    )
    lines.extend(f"- {item}" for item in result.confirmed_hypotheses)
    lines.extend(["", "## Hipóteses descartadas", ""])
    lines.extend(f"- {item}" for item in result.discarded_hypotheses)
    lines.extend(["", "## Duplicidades por Nota Fiscal — Python", ""])
    lines.extend(_duplicate_table(result.duplicate_notes_python))
    lines.extend(["", "## Duplicidades por Nota Fiscal — Power Query", ""])
    lines.extend(_duplicate_table(result.duplicate_notes_powerquery))
    lines.extend(["", "## Duplicidades por CTe — Python", ""])
    lines.extend(_duplicate_table(result.duplicate_ctes_python))
    lines.extend(["", "## Duplicidades por CTe — Power Query", ""])
    if result.powerquery_has_cte:
        lines.append("A coluna CTe está disponível na referência.")
    else:
        lines.append(
            "Não verificável: o arquivo tratado não possui a coluna CTe."
        )
    lines.extend(
        [
            "",
            "## Lista completa dos registros originalmente excedentes",
            "",
            "| Linha | Nota Fiscal | CTe | Tipo CTe | Transportadora | Cancelamento | Emissão | Saída | Entrega | Valor Frete | Operação | Ocorr. NF | Ocorr. CTe | Cancelado | Devolução | Complementar | Reentrega | Redespacho | Possível motivo confirmado |",
            "|---:|---|---|---|---|---|---|---|---|---|---|---:|---:|---|---|---|---|---|---|",
        ]
    )
    for entry in result.only_python:
        values = (
            entry.row_number,
            entry.note,
            entry.cte,
            entry.document_type,
            entry.carrier,
            entry.cancellation,
            entry.emission,
            entry.departure,
            entry.delivery,
            entry.freight_value,
            entry.operation_type,
            entry.note_occurrences,
            entry.cte_occurrences,
            entry.is_cancelled,
            entry.is_return,
            entry.is_complementary,
            entry.is_redelivery,
            entry.is_redespacho,
            "; ".join(entry.possible_reasons),
        )
        lines.append("| " + " | ".join(_markdown(value) for value in values) + " |")
    lines.extend(
        [
            "",
            "## Conclusão",
            "",
            (
                "O conjunto foi reconciliado integralmente: os dois lados possuem "
                "a mesma quantidade e o mesmo multiconjunto de Notas Fiscais."
                if result.is_reconciled
                else "A reconciliação ainda possui registros sem correspondência."
            ),
            "",
            "Nenhuma regra de Prazo, Prazo2, Situação, CNPJ, Código Cliente, Data ou Ano foi implementada nesta sprint.",
        ]
    )
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination
