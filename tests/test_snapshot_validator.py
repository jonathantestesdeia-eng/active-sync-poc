from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from active_sync.exceptions import IncompatibleSnapshotError
from active_sync.transformer.comparator import compare_dataframes
from active_sync.transformer.snapshot_validator import (
    SnapshotStatus,
    validate_snapshot_compatibility,
)
from active_sync.transformer.transforms import build_ano, build_data


def temporal_frame(
    notes: list[str],
    deliveries: list[object],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Nota Fiscal": notes,
            "Saída": ["15/07/2026"] * len(notes),
            "Previsão": ["20/07/2026"] * len(notes),
            "Entrega": deliveries,
        }
    )


def test_compatible_snapshots_have_same_dates_and_nulls() -> None:
    raw = temporal_frame(["1", "2"], ["16/07/2026", None])
    reference = temporal_frame(["1", "2"], [pd.Timestamp("2026-07-16"), None])

    result = validate_snapshot_compatibility(raw, reference)

    assert result.status is SnapshotStatus.COMPATIBLE
    assert result.compatible
    assert result.evidence_for("Entrega").same_date_count == 1
    assert result.evidence_for("Entrega").both_null_count == 1


def test_newer_raw_snapshot_is_temporal_mismatch() -> None:
    raw = temporal_frame(["1", "2"], ["15/07/2026", "16/07/2026"])
    reference = temporal_frame(["1", "2"], ["15/07/2026", None])

    result = validate_snapshot_compatibility(raw, reference)

    evidence = result.evidence_for("Entrega")
    assert result.status is SnapshotStatus.TEMPORAL_MISMATCH
    assert evidence.only_raw_count == 1
    assert evidence.only_reference_count == 0
    assert evidence.raw_only_after_reference_max == 1


def test_newer_reference_snapshot_is_temporal_mismatch() -> None:
    raw = temporal_frame(["1", "2"], ["15/07/2026", None])
    reference = temporal_frame(["1", "2"], ["15/07/2026", "16/07/2026"])

    result = validate_snapshot_compatibility(raw, reference)

    evidence = result.evidence_for("Entrega")
    assert result.status is SnapshotStatus.TEMPORAL_MISMATCH
    assert evidence.only_reference_count == 1
    assert evidence.only_raw_count == 0


def test_conflicting_filled_dates_are_data_divergence() -> None:
    raw = temporal_frame(["1"], ["16/07/2026"])
    reference = temporal_frame(["1"], ["17/07/2026"])

    result = validate_snapshot_compatibility(raw, reference)

    assert result.status is SnapshotStatus.DATA_DIVERGENCE
    assert result.evidence_for("Entrega").conflicting_date_count == 1


def test_mixed_exclusive_directions_are_inconclusive() -> None:
    raw = temporal_frame(
        ["1", "2", "3"],
        ["15/07/2026", "14/07/2026", None],
    )
    reference = temporal_frame(
        ["1", "2", "3"],
        ["15/07/2026", None, "21/07/2026"],
    )

    result = validate_snapshot_compatibility(raw, reference)

    assert result.status is SnapshotStatus.INCONCLUSIVE
    evidence = result.evidence_for("Entrega")
    assert evidence.only_raw_count == 1
    assert evidence.only_reference_count == 1


def test_missing_temporal_column_generates_warning_without_false_failure() -> None:
    raw = temporal_frame(["1"], [None]).drop(columns=["Entrega"])
    reference = temporal_frame(["1"], [None])

    result = validate_snapshot_compatibility(raw, reference)

    assert result.status is SnapshotStatus.COMPATIBLE
    assert any("Entrega" in warning for warning in result.warnings)
    assert {item.column for item in result.columns} == {"Saída", "Previsão"}


def test_invalid_dates_are_recorded_without_mutating_inputs() -> None:
    raw = temporal_frame(["1"], ["data inválida"])
    reference = temporal_frame(["1"], [None])
    raw_before = deepcopy(raw)
    reference_before = deepcopy(reference)

    result = validate_snapshot_compatibility(raw, reference)

    assert result.status is SnapshotStatus.INCONCLUSIVE
    assert result.evidence_for("Entrega").raw_invalid_count == 1
    assert_frame_equal(raw, raw_before)
    assert_frame_equal(reference, reference_before)


def test_time_component_is_ignored() -> None:
    raw = temporal_frame(["1"], [pd.Timestamp("2026-07-16 23:59:59")])
    reference = temporal_frame(["1"], [pd.Timestamp("2026-07-16 00:00:00")])

    result = validate_snapshot_compatibility(raw, reference)

    assert result.status is SnapshotStatus.COMPATIBLE
    assert result.evidence_for("Entrega").same_date_count == 1


def test_duplicate_notes_align_by_occurrence_order() -> None:
    raw = temporal_frame(
        ["1", "1"],
        ["15/07/2026", "16/07/2026"],
    )
    reference = temporal_frame(
        ["1", "1"],
        ["15/07/2026", None],
    )

    result = validate_snapshot_compatibility(raw, reference)

    evidence = result.evidence_for("Entrega")
    assert result.matched_row_count == 2
    assert evidence.same_date_count == 1
    assert evidence.only_raw_count == 1


def test_strict_comparator_raises_controlled_snapshot_error() -> None:
    raw = temporal_frame(["1", "2"], ["15/07/2026", "16/07/2026"])
    reference = temporal_frame(["1", "2"], ["15/07/2026", None])

    with pytest.raises(IncompatibleSnapshotError, match="TEMPORAL_MISMATCH"):
        compare_dataframes(
            raw,
            reference,
            key_columns=["Nota Fiscal"],
            require_compatible_snapshot=True,
        )


def test_comparison_report_places_snapshot_validation_first() -> None:
    raw = temporal_frame(["1", "2"], ["15/07/2026", "16/07/2026"])
    reference = temporal_frame(["1", "2"], ["15/07/2026", None])

    report = compare_dataframes(raw, reference, key_columns=["Nota Fiscal"])
    text = report.to_text(max_divergences=1)

    assert report.snapshot_validation is not None
    assert report.snapshot_validation.status is SnapshotStatus.TEMPORAL_MISMATCH
    assert text.startswith("SNAPSHOT VALIDATION")
    assert text.index("TEMPORAL_MISMATCH") < text.index("RELATÓRIO DE EQUIVALÊNCIA")


def test_data_and_ano_are_fully_equivalent_with_compatible_snapshots() -> None:
    raw = temporal_frame(["1", "2"], ["15/07/2026", None])
    reference = temporal_frame(["1", "2"], ["15/07/2026", None])
    for frame in (raw, reference):
        frame["Data"] = build_data(frame["Entrega"])
        frame["Ano"] = build_ano(frame["Entrega"])

    report = compare_dataframes(raw, reference, key_columns=["Nota Fiscal"])

    assert report.temporally_comparable_row_count == 2
    assert report.temporally_excluded_row_count == 0
    assert report.result_for("Data").equivalence_percent == 100.0
    assert report.result_for("Ano").equivalence_percent == 100.0


def test_data_and_ano_separate_global_from_snapshot_comparable_equivalence() -> None:
    raw = temporal_frame(["1", "2"], ["15/07/2026", "16/07/2026"])
    reference = temporal_frame(["1", "2"], ["15/07/2026", None])
    for frame in (raw, reference):
        frame["Data"] = build_data(frame["Entrega"])
        frame["Ano"] = build_ano(frame["Entrega"])

    report = compare_dataframes(raw, reference, key_columns=["Nota Fiscal"])

    assert report.snapshot_validation is not None
    assert report.snapshot_validation.status is SnapshotStatus.TEMPORAL_MISMATCH
    assert report.temporally_comparable_row_count == 1
    assert report.temporally_excluded_row_count == 1
    for column in ("Data", "Ano"):
        result = report.result_for(column)
        assert result.equivalence_percent == 50.0
        assert result.comparable_equivalence_percent == 100.0
