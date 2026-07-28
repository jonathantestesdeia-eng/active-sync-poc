"""Middlewares transversais de origem, contexto, logging e falhas."""

from __future__ import annotations

import json
import logging
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send


LOGGER = logging.getLogger("active_sync.api")


def error_payload(code: str, message: str, request_id: str | None) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


async def _json_response(
    send: Send,
    status: int,
    payload: dict[str, object],
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
        *(extra_headers or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class OriginValidationMiddleware:
    """Rejeita explicitamente origens que nÃ£o pertencem Ã allowlist."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = next(
            (
                value.decode("latin-1").rstrip("/")
                for key, value in scope.get("headers", [])
                if key.lower() == b"origin"
            ),
            None,
        )
        settings = scope["app"].state.settings
        if origin and origin not in settings.allowed_origins:
            request_id = scope.setdefault("state", {}).get("request_id")
            await _json_response(
                send,
                403,
                error_payload("ORIGIN_NOT_ALLOWED", "Origem nÃ£o permitida", request_id),
            )
            return
        await self.app(scope, receive, send)


class RequestContextMiddleware:
    """Adiciona request ID, log estruturado e Ãºltima barreira de exceÃ§Ãµes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        request_id = next(
            (
                value.decode("latin-1")
                for key, value in scope.get("headers", [])
                if key.lower() == b"x-request-id"
            ),
            str(uuid4()),
        )
        state["request_id"] = request_id
        started_at = perf_counter()
        status_code = 500

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("latin-1", errors="replace"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            settings = scope["app"].state.settings
            LOGGER.error(
                "unhandled_request_error",
                extra={"request_id": request_id, "path": scope.get("path")},
                exc_info=settings.debug,
                stack_info=settings.debug,
            )
            await _json_response(
                send_with_context,
                500,
                error_payload("INTERNAL_ERROR", "Erro interno do servidor", request_id),
            )
        finally:
            LOGGER.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status_code": status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
