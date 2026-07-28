"""Logging seguro para arquivo e terminal."""

from __future__ import annotations

from datetime import datetime
from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging
from pathlib import Path
import sys
from typing import Iterator


_request_id: ContextVar[str | None] = ContextVar(
    "active_sync_request_id", default=None
)


@contextmanager
def request_id_context(request_id: str) -> Iterator[None]:
    """Propaga o identificador para todos os logs da execução corrente."""
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


class TerminalFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        return f"[{timestamp}] {record.getMessage()}"


class JsonFormatter(logging.Formatter):
    """Serializa logs da API em um contrato pesquisÃ¡vel e estÃ¡vel."""

    _standard = frozenset(logging.makeLogRecord({}).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or _request_id.get(),
        }
        for key, value in record.__dict__.items():
            if key not in self._standard and key not in {"message", "asctime"}:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_api_logging(level: str) -> logging.Logger:
    """Configura uma Ãºnica saÃ­da JSON para a aplicaÃ§Ã£o HTTP."""
    logger = logging.getLogger("active_sync.api")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def configure_logging(project_root: Path) -> logging.Logger:
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"active-sync-{datetime.now():%Y%m%d}.log"

    logger = logging.getLogger("active_sync")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    terminal = logging.StreamHandler()
    terminal.setFormatter(TerminalFormatter())

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    )

    logger.addHandler(terminal)
    logger.addHandler(file_handler)
    return logger
