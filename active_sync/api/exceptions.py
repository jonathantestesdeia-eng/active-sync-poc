"""Conversao global e segura de excecoes em respostas HTTP."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from active_sync.services import DashboardError, ServiceError

from .middleware import error_payload


LOGGER = logging.getLogger("active_sync.api")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_payload(code, message, _request_id(request)),
    )


def _caused_by_invalid_query(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        error_type = type(current)
        if (
            error_type.__name__ == "InvalidQueryError"
            and error_type.__module__ == "active_sync.repository.exceptions"
        ):
            return True
        current = current.__cause__
    return False


async def service_error_handler(request: Request, error: ServiceError) -> JSONResponse:
    """Traduz erros esperados sem expor causas internas."""
    LOGGER.error(
        "service_error",
        extra={"request_id": _request_id(request), "error_type": type(error).__name__},
        exc_info=request.app.state.settings.debug,
    )
    if _caused_by_invalid_query(error):
        return _response(request, 422, "INVALID_QUERY", "Parametros de consulta invalidos")
    return _response(request, 503, "SERVICE_UNAVAILABLE", "Servico temporariamente indisponivel")


async def validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    LOGGER.warning(
        "request_validation_error",
        extra={"request_id": _request_id(request), "errors": error.errors()},
    )
    return _response(request, 422, "VALIDATION_ERROR", "Parametros da requisicao invalidos")


async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
    return _response(request, error.status_code, f"HTTP_{error.status_code}", str(error.detail))


async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    LOGGER.error(
        "unhandled_application_error",
        extra={"request_id": _request_id(request), "error_type": type(error).__name__},
        exc_info=request.app.state.settings.debug,
    )
    return _response(request, 500, "INTERNAL_ERROR", "Erro interno do servidor")


def register_exception_handlers(app: FastAPI) -> None:
    """Registra uma politica unica para falhas HTTP e de aplicacao."""
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(DashboardError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
