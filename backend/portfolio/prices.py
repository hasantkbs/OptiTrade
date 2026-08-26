"""
OptiTrade Portfolio Intelligence Platform — price data access.

Reuses `data.fetcher.fetch_history`/`fetch_price_history_range`
directly (the same functions `ml_training.datasets.builder`,
`learning.evaluator`, and `main.py`'s own `/price/{symbol}` endpoint
already use for current/historical price data) rather than a second
price-fetching path. `get_current_price` is Redis-cached with a short
TTL - the "no duplicated calculations" guarantee (requirement 9) for a
single dashboard call that needs the same symbol's current price for
position analytics, risk analytics, and scenario analysis all at once.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

import pandas as pd
import redis

from core.infra_config import redis_retry_disabled, redis_socket_timeout_seconds
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from data.fetcher import fetch_history, fetch_price_history_range
from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError

logger = logging.getLogger(__name__)

_KEY_PREFIX = "portfolio:price"


class PriceService:
    def __init__(
        self,
        config: Optional[PortfolioConfig] = None,
        client: Optional["redis.Redis"] = None,
        current_price_fetcher: Optional[Callable] = None,
        history_fetcher: Optional[Callable] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        timeout = redis_socket_timeout_seconds()
        self._client = client or redis.Redis(
            host=self.config.redis_host, port=self.config.redis_port,
            db=self.config.redis_db, decode_responses=True,
            socket_timeout=timeout, socket_connect_timeout=timeout,
            retry=redis_retry_disabled(), retry_on_error=[],
        )
        self._current_price_fetcher = current_price_fetcher or fetch_history
        self._history_fetcher = history_fetcher or fetch_price_history_range

    def get_current_price(self, symbol: str) -> float:
        symbol = symbol.upper()
        key = f"{_KEY_PREFIX}:{symbol}"
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        history = self._current_price_fetcher(symbol, period="5d")
        if history is None or history.empty:
            raise InsufficientPriceDataError(f"no price data available for {symbol!r}")
        price = float(history["Close"].iloc[-1])
        self._set_cached(key, price)
        return price

    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Current price for every symbol that resolves. A single
        delisted/invalid/unavailable symbol is logged and skipped rather
        than failing the whole batch - mirrors `get_returns()`'s exact
        "silently dropped, not a whole-call failure" philosophy just
        below, since a portfolio holding one bad symbol must not block
        pricing every other position. Missing symbols are simply absent
        from the returned dict - callers that need to know MUST check
        for the symbols they asked for rather than a fabricated price
        for it."""
        prices: Dict[str, float] = {}
        for symbol in symbols:
            try:
                prices[symbol.upper()] = self.get_current_price(symbol)
            except Exception as exc:
                log_event(
                    logger, component="portfolio", module="portfolio.prices", operation="get_current_prices",
                    status=STATUS_ERROR, symbol=symbol.upper(), error_type=type(exc).__name__, level=logging.WARNING,
                )
        return prices

    def get_returns(self, symbols: List[str], lookback_days: Optional[int] = None) -> pd.DataFrame:
        """Daily simple returns for every symbol that had usable price
        history, aligned on common dates. Symbols with no data are
        silently dropped rather than failing the whole call - a single
        illiquid/delisted symbol must not block risk analytics for the
        rest of the portfolio."""
        lookback_days = lookback_days or self.config.lookback_days
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(lookback_days * 1.6))  # buffer for weekends/holidays

        price_data: Dict[str, pd.Series] = {}
        for symbol in symbols:
            history = self._history_fetcher(symbol.upper(), start, end)
            if history is None or history.empty:
                continue
            price_data[symbol.upper()] = history["Close"]

        if not price_data:
            raise InsufficientPriceDataError(
                f"no historical price data available for any of {symbols!r}"
            )

        prices = pd.DataFrame(price_data).dropna()
        returns = prices.pct_change().dropna()
        if returns.empty:
            raise InsufficientPriceDataError("not enough overlapping price history to compute returns")
        return returns

    def _get_cached(self, key: str) -> Optional[float]:
        started_at = time.perf_counter()
        try:
            raw = self._client.get(key)
        except redis.RedisError as exc:
            log_event(
                logger, component="portfolio", module="portfolio.prices", operation="get_cached",
                status=STATUS_ERROR, error_type=type(exc).__name__, level=logging.WARNING,
            )
            return None
        log_event(
            logger, component="portfolio", module="portfolio.prices", operation="get_cached",
            status=STATUS_SUCCESS if raw is not None else "miss",
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return float(raw) if raw is not None else None

    def _set_cached(self, key: str, price: float) -> None:
        try:
            self._client.set(key, price, ex=self.config.price_cache_ttl_seconds)
        except redis.RedisError as exc:
            log_event(
                logger, component="portfolio", module="portfolio.prices", operation="set_cached",
                status=STATUS_ERROR, error_type=type(exc).__name__, level=logging.WARNING,
            )
