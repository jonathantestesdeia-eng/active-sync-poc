"""AutenticaÃ§Ã£o HTTP desacoplada do mecanismo futuro de identidade."""

from __future__ import annotations

from dataclasses import dataclass
import json
from secrets import compare_digest
from typing import Protocol

from starlette.types import ASGIApp, Receive, Scope, Send


API_KEY_HEADER = b"x-api-key"
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/health/database",
        "/health/version",
        "/info",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


class AuthenticationBackend(Protocol):
    """Contrato substituÃ­vel por JWT sem alterar rotas."""

    def authenticate(self, credential: str | None) -> bool:
        """Retorna se a credencial Ã© vÃ¡lida."""


@dataclass(frozen=True, slots=True)
class ApiKeyBackend:
    """Valida API Key em tempo constante."""

    api_key: str | None

    def authenticate(self, credential: str | None) -> bool:
        if not self.api_key or not credential:
            return False
        return compare_digest(credential, self.api_key)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1").strip() or None
    return None


class ApiKeyMiddleware:
    """Protege todas as rotas, exceto a allowlist pÃºblica."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", "")).rstrip("/") or "/"
        if path in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        settings = scope["app"].state.settings
        credential = _header(scope, API_KEY_HEADER)
        if ApiKeyBackend(settings.api_key).authenticate(credential):
            await self.app(scope, receive, send)
            return

        request_id = scope.get("state", {}).get("request_id")
        body = json.dumps(
            {
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Credencial invÃ¡lida ou ausente",
                    "request_id": request_id,
                }
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"www-authenticate", b"ApiKey"),
        ]
        await send({"type": "http.response.start", "status": 401, "headers": headers})
        await send({"type": "http.response.body", "body": body})
