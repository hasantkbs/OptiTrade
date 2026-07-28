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
from watchlist.exceptions import WatchlistItemNotFoundError, WatchlistNotFoundError
from watchlist.models import Watchlist, WatchlistItem
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
