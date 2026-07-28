"""Cliente HTTP persistente da aplicação."""

from __future__ import annotations

import requests

from .config import Settings


class ActiveClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "active-sync-poc/0.1",
                "Accept-Language": "pt-BR,pt;q=0.9",
            }
        )

    def url(self, path: str) -> str:
        return f"{self.settings.base_url}/{path.lstrip('/')}"

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "ActiveClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
