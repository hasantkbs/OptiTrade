"""
OptiTrade Watchlist & Alert Platform — Watchlist Service.

Unlimited watchlists per owner, favorite symbols, folders, tags, and
notes - `WatchlistItem` is a plain per-(watchlist, symbol) row (see
`repository.py`'s `ON CONFLICT (watchlist_id, symbol) DO UPDATE`), so
adding a symbol that's already tracked just updates its favorite/
folder/tags/notes rather than erroring or duplicating.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from watchlist.exceptions import AlertNotFoundError, WatchlistItemNotFoundError, WatchlistNotFoundError
from watchlist.models import Alert, AlertCategory, AlertType, Watchlist, WatchlistItem
from watchlist.repository import WatchlistRepository

logger = logging.getLogger(__name__)


class WatchlistService:
    def __init__(self, repository: Optional[WatchlistRepository] = None) -> None:
        self.repository = repository or WatchlistRepository()

    # ── Watchlists ───────────────────────────────────────────────────────

    def create_watchlist(self, owner: str, name: str) -> Watchlist:
        watchlist = Watchlist(owner=owner, name=name)
        watchlist.id = self.repository.save_watchlist(watchlist)
        log_event(
            logger, component="watchlist", module="watchlist.watchlist_service", operation="create_watchlist",
            status=STATUS_SUCCESS, watchlist_id=watchlist.id, owner=owner,
        )
        return watchlist

    def get_watchlist(self, watchlist_id: int) -> Watchlist:
        watchlist = self.repository.get_watchlist(watchlist_id)
        if watchlist is None:
            raise WatchlistNotFoundError(f"no watchlist with id {watchlist_id!r}")
        return watchlist

    def list_watchlists(self, owner: str) -> List[Watchlist]:
        return self.repository.list_watchlists(owner)

    def delete_watchlist(self, watchlist_id: int) -> None:
        self.get_watchlist(watchlist_id)
        self.repository.delete_watchlist(watchlist_id)
        log_event(
            logger, component="watchlist", module="watchlist.watchlist_service", operation="delete_watchlist",
            status=STATUS_SUCCESS, watchlist_id=watchlist_id,
        )

    # ── Items (favorites / folders / tags / notes) ──────────────────────

    def add_symbol(
        self, watchlist_id: int, symbol: str, is_favorite: bool = False, folder: Optional[str] = None,
        tags: Optional[List[str]] = None, notes: str = "",
    ) -> WatchlistItem:
        self.get_watchlist(watchlist_id)
        item = WatchlistItem(
            watchlist_id=watchlist_id, symbol=symbol, is_favorite=is_favorite, folder=folder,
            tags=tags or [], notes=notes,
        )
        item.id = self.repository.save_item(item)
        log_event(
            logger, component="watchlist", module="watchlist.watchlist_service", operation="add_symbol",
            status=STATUS_SUCCESS, watchlist_id=watchlist_id, symbol=item.symbol,
        )
        return item

    def remove_symbol(self, watchlist_id: int, symbol: str) -> None:
        self.get_watchlist(watchlist_id)
        self.repository.delete_item(watchlist_id, symbol)
        log_event(
            logger, component="watchlist", module="watchlist.watchlist_service", operation="remove_symbol",
            status=STATUS_SUCCESS, watchlist_id=watchlist_id, symbol=symbol.upper(),
        )

    def get_item(self, watchlist_id: int, symbol: str) -> WatchlistItem:
        item = self.repository.get_item(watchlist_id, symbol)
        if item is None:
            raise WatchlistItemNotFoundError(f"symbol {symbol.upper()!r} not found in watchlist {watchlist_id!r}")
        return item

    def list_items(self, watchlist_id: int) -> List[WatchlistItem]:
        self.get_watchlist(watchlist_id)
        return self.repository.list_items(watchlist_id)

    def list_favorites(self, watchlist_id: int) -> List[WatchlistItem]:
        return [item for item in self.list_items(watchlist_id) if item.is_favorite]

    def list_by_folder(self, watchlist_id: int, folder: str) -> List[WatchlistItem]:
        return [item for item in self.list_items(watchlist_id) if item.folder == folder]

    def list_by_tag(self, watchlist_id: int, tag: str) -> List[WatchlistItem]:
        return [item for item in self.list_items(watchlist_id) if tag in item.tags]

    def set_favorite(self, watchlist_id: int, symbol: str, is_favorite: bool) -> WatchlistItem:
        item = self.get_item(watchlist_id, symbol)
        item.is_favorite = is_favorite
        item.id = self.repository.save_item(item)
        return item

    def set_folder(self, watchlist_id: int, symbol: str, folder: Optional[str]) -> WatchlistItem:
        item = self.get_item(watchlist_id, symbol)
        item.folder = folder
        item.id = self.repository.save_item(item)
        return item

    def set_tags(self, watchlist_id: int, symbol: str, tags: List[str]) -> WatchlistItem:
        item = self.get_item(watchlist_id, symbol)
        item.tags = tags
        item.id = self.repository.save_item(item)
        return item

    def set_notes(self, watchlist_id: int, symbol: str, notes: str) -> WatchlistItem:
        item = self.get_item(watchlist_id, symbol)
        item.notes = notes
        item.id = self.repository.save_item(item)
        return item

    # ── Alerts ───────────────────────────────────────────────────────────
    #
    # Alert *evaluation* lives in alert_engine.py/price_alerts.py/etc. and
    # is driven by scheduler.py:AlertScheduler; these are the plain CRUD
    # operations a caller needs to actually define an alert in the first
    # place, following the exact same thin-wrapper-over-the-repository
    # shape as the watchlist/item methods above.

    def create_alert(
        self, owner: str, category: AlertCategory, alert_type: AlertType, parameters: Optional[dict] = None,
        watchlist_id: Optional[int] = None, symbol: Optional[str] = None, portfolio_id: Optional[int] = None,
        cooldown_minutes: int = 60,
    ) -> Alert:
        if watchlist_id is not None:
            self.get_watchlist(watchlist_id)
        alert = Alert(
            owner=owner, watchlist_id=watchlist_id, symbol=symbol, portfolio_id=portfolio_id, category=category,
            alert_type=alert_type, parameters=parameters or {}, cooldown_minutes=cooldown_minutes,
        )
        alert.id = self.repository.save_alert(alert)
        log_event(
            logger, component="watchlist", module="watchlist.watchlist_service", operation="create_alert",
            status=STATUS_SUCCESS, alert_id=alert.id, owner=owner, category=category.value, alert_type=alert_type.value,
        )
        return alert

    def get_alert(self, alert_id: int) -> Alert:
        alert = self.repository.get_alert(alert_id)
        if alert is None:
            raise AlertNotFoundError(f"no alert with id {alert_id!r}")
        return alert

    def list_alerts(self, owner: str, watchlist_id: Optional[int] = None) -> List[Alert]:
        alerts = self.repository.list_alerts(owner=owner)
        if watchlist_id is not None:
            alerts = [alert for alert in alerts if alert.watchlist_id == watchlist_id]
        return alerts

    def set_alert_enabled(self, alert_id: int, enabled: bool) -> Alert:
        alert = self.get_alert(alert_id)
        self.repository.set_alert_enabled(alert_id, enabled)
        alert.enabled = enabled
        log_event(
            logger, component="watchlist", module="watchlist.watchlist_service", operation="set_alert_enabled",
            status=STATUS_SUCCESS, alert_id=alert_id, enabled=enabled,
        )
        return alert

    def delete_alert(self, alert_id: int) -> None:
        self.get_alert(alert_id)
        self.repository.delete_alert(alert_id)
        log_event(
            logger, component="watchlist", module="watchlist.watchlist_service", operation="delete_alert",
            status=STATUS_SUCCESS, alert_id=alert_id,
        )
