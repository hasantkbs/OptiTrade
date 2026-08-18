"""
OptiTrade Watchlist & Alert Platform — News Alerts.

Reuses `engines.news.engine.NewsEngine.analyze` directly for every
check - the same aggregated sentiment/impact/relevance/evidence the
live News Engine already computes, never a second news-scoring path.
Sector grouping reuses `core.sector_intelligence.SECTOR_DEFINITIONS`
(the same source `portfolio.classification.sector_for_symbol` already
reverse-indexes) for the forward symbol-list-per-sector lookup.

Redis-caches each symbol's `NewsAnalysisResult` for a short TTL -
`news_high_impact`/`news_breaking` alerts on the same symbol, or a
`news_sector` alert whose sector overlaps another alert's symbol,
would otherwise redundantly re-fetch live news for the same symbol
multiple times within one scheduler scan (see `portfolio.prices.
PriceService`'s identical rationale for its own current-price cache).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import redis

from core.sector_intelligence import SECTOR_DEFINITIONS
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from engines.news.engine import NewsEngine
from engines.news.models import NewsAnalysisResult
from portfolio.classification import sector_for_symbol
from watchlist.config import WatchlistConfig
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertTriggerEvent, AlertType

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "watchlist:news_analysis"


def default_symbols_for_sector(sector: str) -> List[str]:
    definition = SECTOR_DEFINITIONS.get(sector)
    if definition is None:
        return []
    return list(definition.get("tr_symbols", [])) + list(definition.get("us_symbols", []))


class NewsAlertEvaluator:
    def __init__(
        self,
        news_engine: Optional[NewsEngine] = None,
        sector_symbols_provider: Optional[Callable[[str], List[str]]] = None,
        redis_client: Optional["redis.Redis"] = None,
        config: Optional[WatchlistConfig] = None,
    ) -> None:
        self.config = config or WatchlistConfig.from_env()
        self.news_engine = news_engine or NewsEngine()
        self.sector_symbols_provider = sector_symbols_provider or default_symbols_for_sector
        self._redis_client = redis_client or redis.Redis(
            host=self.config.redis_host, port=self.config.redis_port, db=self.config.redis_db,
            decode_responses=True,
        )

    def _analyze(self, symbol: str) -> NewsAnalysisResult:
        key = f"{_CACHE_KEY_PREFIX}:{symbol.upper()}"
        try:
            cached = self._redis_client.get(key)
        except redis.RedisError as exc:
            cached = None
            log_event(
                logger, component="watchlist", module="watchlist.news_alerts", operation="analyze_cache_get",
                status=STATUS_ERROR, symbol=symbol, error_type=type(exc).__name__, level=logging.WARNING,
            )
        if cached is not None:
            return NewsAnalysisResult.model_validate_json(cached)

        analysis = self.news_engine.analyze(symbol)
        try:
            self._redis_client.set(key, analysis.model_dump_json(), ex=self.config.news_cache_ttl_seconds)
        except redis.RedisError as exc:
            log_event(
                logger, component="watchlist", module="watchlist.news_alerts", operation="analyze_cache_set",
                status=STATUS_ERROR, symbol=symbol, error_type=type(exc).__name__, level=logging.WARNING,
            )
        else:
            log_event(
                logger, component="watchlist", module="watchlist.news_alerts", operation="analyze_cache_set",
                status=STATUS_SUCCESS, symbol=symbol,
            )
        return analysis

    def evaluate(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if alert.category != AlertCategory.NEWS:
            raise InvalidAlertError(f"NewsAlertEvaluator cannot evaluate category {alert.category!r}")

        if alert.alert_type == AlertType.NEWS_HIGH_IMPACT:
            return self._high_impact_check(alert)
        if alert.alert_type == AlertType.NEWS_BREAKING:
            return self._breaking_check(alert)
        if alert.alert_type == AlertType.NEWS_SECTOR:
            return self._sector_check(alert)
        raise InvalidAlertError(f"unsupported news alert_type {alert.alert_type!r}")

    def _high_impact_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if not alert.symbol:
            raise InvalidAlertError("news_high_impact alerts require a symbol")
        analysis = self._analyze(alert.symbol)
        new_state = {"impact": analysis.impact, "article_count": float(analysis.article_count)}

        threshold = alert.parameters.get("threshold", self.config.news_high_impact_threshold)
        if analysis.article_count == 0 or analysis.impact < threshold:
            return None, new_state

        event = self._event(
            alert, f"{alert.symbol} high-impact news (impact={analysis.impact:.2f}, {analysis.article_count} articles)",
            {"impact": analysis.impact, "relevance": analysis.relevance, "threshold": threshold},
        )
        return event, new_state

    def _breaking_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if not alert.symbol:
            raise InvalidAlertError("news_breaking alerts require a symbol")
        analysis = self._analyze(alert.symbol)
        max_age_minutes = alert.parameters.get("max_age_minutes", self.config.news_breaking_max_age_minutes)
        now = datetime.now(timezone.utc)

        recent = [
            item for item in analysis.structured_evidence
            if (now - item.timestamp).total_seconds() <= max_age_minutes * 60
        ]
        new_state = {"recent_article_count": float(len(recent))}
        if not recent:
            return None, new_state

        most_recent = max(recent, key=lambda item: item.timestamp)
        age_minutes = (now - most_recent.timestamp).total_seconds() / 60
        event = self._event(
            alert, f"Breaking news for {alert.symbol}: {most_recent.title}",
            {"age_minutes": age_minutes, "impact": most_recent.impact, "sentiment": most_recent.sentiment},
        )
        return event, new_state

    def _sector_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if not alert.symbol:
            raise InvalidAlertError("news_sector alerts require a symbol representative of the sector")
        sector = sector_for_symbol(alert.symbol)
        symbols = self.sector_symbols_provider(sector)
        if not symbols:
            raise InsufficientAlertDataError(f"no known symbols for sector {sector!r}")

        impacts: List[float] = []
        for symbol in symbols:
            try:
                analysis = self._analyze(symbol)
            except Exception as exc:
                # Not logged before - a single symbol's News Engine
                # failure was indistinguishable from "checked and
                # found nothing", and a sector-wide outage (every
                # symbol failing) was silently reported as
                # sector_impact=0.0 with zero observability.
                log_event(
                    logger, component="watchlist", module="watchlist.news_alerts", operation="sector_check_analyze",
                    status=STATUS_ERROR, symbol=symbol, sector=sector, error_type=type(exc).__name__,
                    level=logging.WARNING,
                )
                continue
            if analysis.article_count > 0:
                impacts.append(analysis.impact)

        if not impacts:
            return None, {"sector_impact": 0.0}

        average_impact = sum(impacts) / len(impacts)
        new_state = {"sector_impact": average_impact}
        threshold = alert.parameters.get("threshold", self.config.news_sector_impact_threshold)
        if average_impact < threshold:
            return None, new_state

        event = self._event(
            alert, f"{sector} sector news impact {average_impact:.2f} exceeds {threshold:.2f}",
            {"sector_impact": average_impact, "threshold": threshold, "symbol_count": float(len(impacts))},
        )
        return event, new_state

    @staticmethod
    def _event(alert: Alert, message: str, evidence: Dict[str, float]) -> AlertTriggerEvent:
        return AlertTriggerEvent(
            alert_id=alert.id, owner=alert.owner, symbol=alert.symbol, category=alert.category,
            alert_type=alert.alert_type, message=message, evidence=evidence,
        )
