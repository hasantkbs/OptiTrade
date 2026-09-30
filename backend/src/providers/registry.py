"""
OptiTrade — Provider Registry
================================
Single access point for the active market data provider.

get_market_provider() always returns an object that satisfies
the MarketDataProvider Protocol.  Swap the implementation here
without touching any business logic.

Usage:
    from providers.registry import get_market_provider

    provider = get_market_provider()
    hist = provider.fetch_ohlcv("AAPL", period="6mo")
"""
from __future__ import annotations

import os
import threading
from typing import Optional

from providers.base import MarketDataProvider

_provider: Optional[MarketDataProvider] = None
_lock = threading.Lock()


def get_market_provider() -> MarketDataProvider:
    """Return the singleton MarketDataProvider instance (double-checked locking)."""
    global _provider
    if _provider is None:
        with _lock:
            if _provider is None:
                _provider = _create_provider()
    return _provider


def _create_provider() -> MarketDataProvider:
    """
    Instantiate the provider chosen by the MARKET_DATA_PROVIDER env var.
    Defaults to HybridProvider (BIST->yfinance, crypto->Binance,
    US->Finnhub if FINNHUB_API_KEY is set, else yfinance).
    Extend this function to add more providers.
    """
    name = os.getenv("MARKET_DATA_PROVIDER", "HYBRID").upper()
    if name == "HYBRID":
        from providers.hybrid_provider import HybridProvider
        return HybridProvider()
    if name == "YFINANCE":
        from providers.yfinance_provider import YFinanceProvider
        return YFinanceProvider()
    raise ValueError(
        f"Unknown market data provider: '{name}'. "
        f"Supported values: HYBRID, YFINANCE"
    )


def override_provider(provider: MarketDataProvider) -> None:
    """
    Replace the singleton for testing purposes.
    Call reset_provider() after the test to restore the default.
    """
    global _provider
    _provider = provider


def reset_provider() -> None:
    """Reset the singleton so the next call to get_market_provider() recreates it."""
    global _provider
    _provider = None
