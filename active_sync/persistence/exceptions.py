"""Exceções específicas da camada de persistência."""


class PersistenceError(Exception):
    """Erro base da camada de persistência."""


class DatabaseConnectionError(PersistenceError):
    """Indica uso ou abertura inválida de uma conexão."""


class MigrationError(PersistenceError):
    """Indica falha ao criar ou validar a estrutura persistente."""


class DataFramePersistenceError(PersistenceError):
    """Indica que um DataFrame não respeita o contrato persistente."""
