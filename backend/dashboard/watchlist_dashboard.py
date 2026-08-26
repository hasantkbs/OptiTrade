"""OptiTrade Analytics & Dashboard Platform — Watchlist dashboard."""
from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from dashboard.models import WatchlistDashboardView
from watchlist.watchlist_service import WatchlistService

logger = logging.getLogger(__name__)
_MODULE = "dashboard.watchlist_dashboard"
_COMPONENT = "dashboard"


class WatchlistDashboardService:
    def __init__(self, watchlist_service: Optional[WatchlistService] = None) -> None:
        self._watchlist_service = watchlist_service or WatchlistService()

    def build(self, owner: str, top_n: int = 10) -> WatchlistDashboardView:
        started_at = time.perf_counter()
        watchlists = self._watchlist_service.list_watchlists(owner)

        all_items = []
        items_by_folder: dict = {}
        for watchlist in watchlists:
            items = self._watchlist_service.list_items(watchlist.id)
            all_items.extend(items)
            for item in items:
                folder = item.folder or "Unfoldered"
                items_by_folder[folder] = items_by_folder.get(folder, 0) + 1

        symbol_counts = Counter(item.symbol for item in all_items)
        view = WatchlistDashboardView(
            total_watchlists=len(watchlists), total_items=len(all_items),
            total_favorites=sum(1 for item in all_items if item.is_favorite),
            most_tracked_symbols=[symbol for symbol, _ in symbol_counts.most_common(top_n)],
            items_by_folder=items_by_folder,
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, owner=owner,
        )
        return view
