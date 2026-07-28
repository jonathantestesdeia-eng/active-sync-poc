"""Camada independente de transformação para Performance Entrega."""

from .columns import OUTPUT_COLUMNS
from .comparator import (
    CellDivergence,
    ColumnComparison,
    ComparisonReport,
    compare_dataframes,
    write_comparison_report,
)
from .exporter import export_validation_excel
from .reconciliation import (
    DuplicateGroup,
    ReconciliationEntry,
    ReconciliationResult,
    ReconciliationRules,
    apply_reconciliation_rules,
    infer_reconciliation_rules,
    reconcile_datasets,
    write_reconciliation_markdown,
)
from .snapshot_validator import (
    SnapshotStatus,
    SnapshotValidationResult,
    TemporalColumnEvidence,
    validate_snapshot_compatibility,
    write_snapshot_validation_report,
)
from .returns import build_cte_devolucao, build_flag_devolucao_nf, build_tipo_cte
from .schema import (
    ColumnSchema,
    ColumnStatus,
    TRANSFORMER_SCHEMA,
    postgresql_ddl,
    schema_markdown,
    sqlite_ddl,
    write_schema_markdown,
)
from .situation import build_situacao
from .transforms import (
    build_cnpj,
    build_codigo_cliente,
    build_data,
    build_destinatario,
    build_entrega,
    build_ano,
    build_prazo,
    build_prazo2,
    build_transportadora,
    transform_dataframe,
)
from .validator import ValidationResult, validate_output_dataframe, validate_source_dataframe

__all__ = [
    "OUTPUT_COLUMNS",
    "CellDivergence",
    "ColumnSchema",
    "ColumnComparison",
    "ColumnStatus",
    "ComparisonReport",
    "DuplicateGroup",
    "ReconciliationEntry",
    "ReconciliationResult",
    "ReconciliationRules",
    "SnapshotStatus",
    "SnapshotValidationResult",
    "TemporalColumnEvidence",
    "TRANSFORMER_SCHEMA",
    "ValidationResult",
    "compare_dataframes",
    "apply_reconciliation_rules",
    "build_cnpj",
    "build_codigo_cliente",
    "build_cte_devolucao",
    "build_data",
    "build_destinatario",
    "build_entrega",
    "build_flag_devolucao_nf",
    "build_ano",
    "build_prazo",
    "build_prazo2",
    "build_situacao",
    "build_transportadora",
    "build_tipo_cte",
    "export_validation_excel",
    "infer_reconciliation_rules",
    "postgresql_ddl",
    "reconcile_datasets",
    "schema_markdown",
    "sqlite_ddl",
    "transform_dataframe",
    "validate_output_dataframe",
    "validate_snapshot_compatibility",
    "validate_source_dataframe",
    "write_comparison_report",
    "write_reconciliation_markdown",
    "write_schema_markdown",
    "write_snapshot_validation_report",
]
