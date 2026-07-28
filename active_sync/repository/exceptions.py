"""Exceções específicas da camada Repository."""


class RepositoryError(Exception):
    """Erro base das consultas do Repository."""


class InvalidQueryError(RepositoryError, ValueError):
    """Indica filtro, período, ordenação ou paginação inválidos."""
