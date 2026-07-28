"""API pública da camada de persistência."""

from .database import DatabaseManager
from .exceptions import (
    DatabaseConnectionError,
    DataFramePersistenceError,
    MigrationError,
    PersistenceError,
)
from .migrations import (
    MigrationManager,
    PERFORMANCE_TABLE,
    SCHEMA_MIGRATIONS_TABLE,
    SUPERTRACK_TABLE,
)
from .supertrack import (
    SUPERTRACK_COLUMNS,
    SUPERTRACK_KEY_COLUMNS,
    SuperTrackMergeResult,
    delete_supertrack_movements,
    merge_supertrack_movements,
)
from .writer import MergeResult, merge_dataframe, persist_dataframe

__all__ = [
    "DatabaseConnectionError",
    "DatabaseManager",
    "DataFramePersistenceError",
    "MigrationError",
    "MigrationManager",
    "MergeResult",
    "PERFORMANCE_TABLE",
    "SCHEMA_MIGRATIONS_TABLE",
    "SUPERTRACK_COLUMNS",
    "SUPERTRACK_KEY_COLUMNS",
    "SUPERTRACK_TABLE",
    "SuperTrackMergeResult",
    "PersistenceError",
    "merge_dataframe",
    "merge_supertrack_movements",
    "delete_supertrack_movements",
    "persist_dataframe",
]
