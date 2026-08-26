"""OptiTrade Analytics & Dashboard Platform — Market dashboard."""
from __future__ import annotations

import logging
import time
from collections import Counter
from typing import List, Optional

from core.news_analyzer import get_news_summary
from core.regime_scanner import MarketRegimeScanner
from core.sector_intelligence import get_sector_overview
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from dashboard.config import DashboardConfig
from dashboard.models import MarketDashboardView, NewsImpactSnapshot, SectorSnapshot
from feature_store.service import FeatureStoreService, get_default_feature_store_service

logger = logging.getLogger(__name__)
_MODULE = "dashboard.market_dashboard"
_COMPONENT = "dashboard"

_VOLATILITY_FEATURE_NAME = "atr_pct"


class MarketDashboardService:
    def __init__(
        self,
        regime_scanner: Optional[MarketRegimeScanner] = None,
        feature_store: Optional[FeatureStoreService] = None,
        config: Optional[DashboardConfig] = None,
    ) -> None:
        self._regime_scanner = regime_scanner or MarketRegimeScanner()
        self._feature_store = feature_store or get_default_feature_store_service()
        self._config = config or DashboardConfig.from_env()

    def build(self, symbols: Optional[List[str]] = None, market: str = "US") -> MarketDashboardView:
        started_at = time.perf_counter()
        symbols = symbols or list(self._config.default_market_symbols)

        scanned = self._regime_scanner.scan(symbols)
        regime_distribution = dict(Counter(scanned_symbol.regime.value for scanned_symbol in scanned))

        volatility_map = {}
        for symbol in symbols:
            try:
                record = self._feature_store.get_latest_feature(symbol, _VOLATILITY_FEATURE_NAME)
            except Exception as exc:
                log_event(
                    logger, component=_COMPONENT, module=_MODULE, operation="get_latest_feature", status=STATUS_ERROR,
                    error_type=type(exc).__name__, symbol=symbol, level=logging.WARNING,
                )
                continue
            if record is not None:
                volatility_map[symbol] = record.value

        sector_heatmap = [
            SectorSnapshot(
                sector=result.sector, opportunity_score=result.opportunity_score,
                avg_change_pct=result.avg_change_pct, trend=result.trend,
            )
            for result in get_sector_overview(market=market)
        ]

        news_impact_summary = []
        for symbol in symbols:
            try:
                summary = get_news_summary(symbol)
            except Exception as exc:
                log_event(
                    logger, component=_COMPONENT, module=_MODULE, operation="get_news_summary", status=STATUS_ERROR,
                    error_type=type(exc).__name__, symbol=symbol, level=logging.WARNING,
                )
                continue
            news_impact_summary.append(
                NewsImpactSnapshot(
                    symbol=symbol, sentiment_score=summary.get("sentiment_score", 0.0),
                    sentiment_label=summary.get("sentiment_label", "neutral"),
                    headline_count=len(summary.get("headlines", [])),
                )
            )

        view = MarketDashboardView(
            regime_distribution=regime_distribution, volatility_map=volatility_map, sector_heatmap=sector_heatmap,
            news_impact_summary=news_impact_summary,
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, symbol_count=len(symbols),
        )
        return view
