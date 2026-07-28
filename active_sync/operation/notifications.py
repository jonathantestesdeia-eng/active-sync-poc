"""Contratos de notificação operacional, sem transporte externo nesta Sprint."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import logging
from typing import Mapping, Protocol


class SyncNotificationType(StrEnum):
    COMPLETED = "sync_completed"
    FAILED = "sync_failed"
    INVALID_FILE = "invalid_file"
    DATABASE_UNAVAILABLE = "database_unavailable"


@dataclass(frozen=True, slots=True)
class SyncNotification:
    event: SyncNotificationType
    request_id: str
    occurred_at: datetime
    details: Mapping[str, object]


class SyncNotifier(Protocol):
    """Porta preparada para e-mail, webhook ou mensageria futura."""

    def notify(self, notification: SyncNotification) -> None: ...


class LoggingSyncNotifier:
    """Implementação local: registra o evento sem realizar envio externo."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def notify(self, notification: SyncNotification) -> None:
        level = (
            logging.ERROR
            if notification.event
            in {
                SyncNotificationType.FAILED,
                SyncNotificationType.DATABASE_UNAVAILABLE,
            }
            else logging.WARNING
            if notification.event is SyncNotificationType.INVALID_FILE
            else logging.INFO
        )
        self.logger.log(
            level,
            "operational_notification",
            extra={
                "request_id": notification.request_id,
                "notification_type": notification.event.value,
                **dict(notification.details),
            },
        )
