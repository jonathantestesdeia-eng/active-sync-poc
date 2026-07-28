"""Exceções públicas da camada Services."""


class ServiceError(Exception):
    """Erro ao coordenar uma operação de consulta."""


class DashboardError(ServiceError):
    """Erro ao calcular indicadores do dashboard."""
