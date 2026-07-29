"""
OptiTrade Analytics & Dashboard Platform — cache-refresh scheduler.

Periodically recomputes the more expensive, frequently-polled dashboard
views (overview, market) and pushes them into Redis under their own
TTL, matching the caching convention `portfolio/prices.py`'s
`PriceService` already established. Cheap per-request views (portfolio/
paper trading/watchlist dashboards, all scoped to one account/owner)
are not cached here - they're already fast and account-specific.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional

import redis

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from dashboard.config import DashboardConfig
from dashboard.engine_dashboard import EngineDashboardService
from dashboard.market_dashboard import MarketDashboardService
from dashboard.models import EngineDashboardView, MarketDashboardView, OverviewMetrics
from dashboard.overview import OverviewDashboardService

logger = logging.getLogger(__name__)
_MODULE = "dashboard.scheduler"
_COMPONENT = "dashboard"

_OVERVIEW_CACHE_KEY = "dashboard:overview"
_MARKET_CACHE_KEY = "dashboard:market"
_ENGINE_CACHE_KEY = "dashboard:engine"


class DashboardScheduler:
    def __init__(
        self,
        overview_service: OverviewDashboardService,
        market_dashboard_service: MarketDashboardService,
        engine_dashboard_service: EngineDashboardService,
        redis_client: Optional["redis.Redis"] = None,
        config: Optional[DashboardConfig] = None,
    ) -> None:
        self._overview_service = overview_service
        self._market_dashboard_service = market_dashboard_service
        self._engine_dashboard_service = engine_dashboard_service
        self._config = config or DashboardConfig.from_env()
        self._client = redis_client or redis.Redis(
            host=self._config.redis_host, port=self._config.redis_port, db=self._config.redis_db,
            decode_responses=True,
        )

    def refresh_overview_cache(self) -> OverviewMetrics:
        metrics = self._overview_service.build()
        self._set_cached(_OVERVIEW_CACHE_KEY, metrics.model_dump_json(), self._config.overview_cache_ttl_seconds)
        return metrics

    def refresh_market_cache(self, symbols=None) -> MarketDashboardView:
        view = self._market_dashboard_service.build(symbols=symbols)
        self._set_cached(_MARKET_CACHE_KEY, view.model_dump_json(), self._config.dashboard_cache_ttl_seconds)
        return view

    def refresh_engine_cache(self, regime_symbols=None) -> EngineDashboardView:
        view = self._engine_dashboard_service.build(regime_symbols=regime_symbols)
        self._set_cached(_ENGINE_CACHE_KEY, view.model_dump_json(), self._config.dashboard_cache_ttl_seconds)
        return view

    def get_cached_overview(self) -> Optional[str]:
        return self._get_cached(_OVERVIEW_CACHE_KEY)

    def get_cached_market(self) -> Optional[str]:
        return self._get_cached(_MARKET_CACHE_KEY)

    def get_cached_engine(self) -> Optional[str]:
        return self._get_cached(_ENGINE_CACHE_KEY)

    def refresh_all(self) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for name, refresh in (
            ("overview", self.refresh_overview_cache),
            ("market", self.refresh_market_cache),
            ("engine", self.refresh_engine_cache),
        ):
            started_at = time.perf_counter()
            try:
                refresh()
                results[name] = True
                log_event(
                    logger, component=_COMPONENT, module=_MODULE, operation="refresh_all", status=STATUS_SUCCESS,
                    execution_time_ms=(time.perf_counter() - started_at) * 1000, view=name,
                )
            except Exception as exc:
                results[name] = False
                log_event(
                    logger, component=_COMPONENT, module=_MODULE, operation="refresh_all", status=STATUS_ERROR,
                    error_type=type(exc).__name__, view=name, level=logging.ERROR,
                )
        return results

    def _get_cached(self, key: str) -> Optional[str]:
        try:
            return self._client.get(key)
        except redis.RedisError as exc:
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="get_cached", status=STATUS_ERROR,
                error_type=type(exc).__name__, level=logging.WARNING,
            )
            return None

    def _set_cached(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            self._client.set(key, value, ex=ttl_seconds)
        except redis.RedisError as exc:
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="set_cached", status=STATUS_ERROR,
                error_type=type(exc).__name__, level=logging.WARNING,
            )
