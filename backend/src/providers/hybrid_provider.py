"""
OptiTrade — Hybrid MarketDataProvider
=======================================
Routes each symbol to the data source best suited for its market:

  - BIST  (".IS" suffix)      -> YFinanceProvider  (no free alternative covers BIST)
  - Crypto ("-USD" suffix)    -> BinanceProvider    (free, no key, reliable OHLCV)
  - Everything else (US/JP…)  -> FinnhubProvider if FINNHUB_API_KEY is set,
                                  otherwise falls back to YFinanceProvider

This means HybridProvider is safe to use as the default even without a
Finnhub key configured — it behaves exactly like YFinanceProvider until
one is added.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd

from providers.binance_provider import BinanceProvider
from providers.finnhub_provider import FinnhubProvider
from providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)


class HybridProvider:
    """Satisfies the MarketDataProvider Protocol by delegating per symbol."""

    def __init__(self) -> None:
        self._yfinance = YFinanceProvider()
        self._binance  = BinanceProvider()
        self._finnhub  = FinnhubProvider()
        self._finnhub_enabled = bool(os.getenv("FINNHUB_API_KEY"))

    def _route(self, symbol: str):
        sym = symbol.upper()
        if sym.endswith(".IS") or sym.endswith(".T"):
            return self._yfinance
        if sym.endswith("-USD"):
            return self._binance
        if self._finnhub_enabled:
            return self._finnhub
        return self._yfinance

    def fetch_ohlcv(self, symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
        provider = self._route(symbol)
        result = provider.fetch_ohlcv(symbol, period=period)
        if result is None and provider is not self._yfinance:
            logger.info("Falling back to yfinance OHLCV for %s", symbol)
            return self._yfinance.fetch_ohlcv(symbol, period=period)
        return result

    def fetch_info(self, symbol: str) -> dict:
        provider = self._route(symbol)
        result = provider.fetch_info(symbol)
        if not result and provider is not self._yfinance:
            return self._yfinance.fetch_info(symbol)
        return result

    def get_balance_status(self, symbol: str) -> str:
        provider = self._route(symbol)
        status = provider.get_balance_status(symbol)
        if status == "Notr" and provider is not self._yfinance:
            return self._yfinance.get_balance_status(symbol)
        return status
