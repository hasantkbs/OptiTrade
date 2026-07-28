"""
OptiTrade Watchlist & Alert Platform — Notification Router.

Prepares notification payloads only - `NotificationProvider` is a
structural interface a real Firebase/APNS implementation will satisfy
later; this platform never sends a push notification anywhere.
`InMemoryNotificationProvider` is the only concrete provider here, and
deliberately makes no external call of any kind.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Protocol, runtime_checkable

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from watchlist.config import WatchlistConfig
from watchlist.models import AlertCategory, AlertTriggerEvent, NotificationPayload

logger = logging.getLogger(__name__)

_TITLE_BY_CATEGORY = {
    AlertCategory.PRICE: "Price Alert",
    AlertCategory.TECHNICAL: "Technical Alert",
    AlertCategory.DECISION: "Decision Engine Alert",
    AlertCategory.NEWS: "News Alert",
    AlertCategory.PORTFOLIO: "Portfolio Alert",
}


@runtime_checkable
class NotificationProvider(Protocol):
    """Structural interface any real provider (Firebase Cloud Messaging,
    APNS, email, ...) will implement - never implemented here."""

    def send(self, payload: NotificationPayload) -> bool: ...


class InMemoryNotificationProvider:
    """The only concrete provider this platform ships - records
    prepared payloads in-process (useful for tests/inspection/an admin
    endpoint) and makes no external call whatsoever."""

    def __init__(self) -> None:
        self.sent: List[NotificationPayload] = []

    def send(self, payload: NotificationPayload) -> bool:
        self.sent.append(payload)
        log_event(
            logger, component="watchlist", module="watchlist.notification_router", operation="send",
            status=STATUS_SUCCESS, alert_id=payload.alert_id, owner=payload.owner,
        )
        return True


class NotificationRouter:
    def __init__(
        self, providers: Optional[List[NotificationProvider]] = None, config: Optional[WatchlistConfig] = None,
    ) -> None:
        self.config = config or WatchlistConfig.from_env()
        self.providers: List[NotificationProvider] = (
            providers if providers is not None else [InMemoryNotificationProvider()]
        )

    def build_payload(self, event: AlertTriggerEvent) -> NotificationPayload:
        data = {"category": event.category.value, "alert_type": event.alert_type.value}
        if event.symbol:
            data["symbol"] = event.symbol
        if event.portfolio_id is not None:
            data["portfolio_id"] = str(event.portfolio_id)
        if event.related_decision is not None:
            data["decision"] = event.related_decision.value

        title = _TITLE_BY_CATEGORY.get(event.category, "Alert")
        if event.symbol:
            title = f"{title}: {event.symbol}"

        return NotificationPayload(
            alert_id=event.alert_id, owner=event.owner, title=title, body=event.message, data=data,
            severity=event.severity,
        )

    def route(self, event: AlertTriggerEvent) -> NotificationPayload:
        """Builds the payload once and hands it to every registered
        provider - one provider failing to accept it never blocks the
        others."""
        payload = self.build_payload(event)
        for provider in self.providers:
            try:
                provider.send(payload)
            except Exception as exc:
                log_event(
                    logger, component="watchlist", module="watchlist.notification_router", operation="route",
                    status=STATUS_ERROR, alert_id=event.alert_id, provider=type(provider).__name__,
                    error_type=type(exc).__name__, level=logging.WARNING,
                )
                continue
        return payload
