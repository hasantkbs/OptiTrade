"""
OptiTrade — Data Fetcher
==========================
Thin adapter layer.  All callers (analyzer.py, main.py, etc.) use these
functions without knowing which provider is active.

The active provider is resolved via providers.registry.get_market_provider().
To swap providers, set the MARKET_DATA_PROVIDER env var and restart.
"""
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def fetch_history(symbol: str, period: str = "1mo") -> Optional[pd.DataFrame]:
    """Return OHLCV DataFrame for the given symbol and period, or None."""
    from providers.registry import get_market_provider
    return get_market_provider().fetch_ohlcv(symbol, period=period)


def fetch_info(symbol: str) -> dict:
    """Return fundamental / metadata dict for the symbol, or {}."""
    from providers.registry import get_market_provider
    return get_market_provider().fetch_info(symbol)


def get_balance_status(symbol: str) -> str:
    """Return 'Pozitif' | 'Negatif' | 'Notr' based on EPS trend."""
    from providers.registry import get_market_provider
    return get_market_provider().get_balance_status(symbol)


def fetch_bist100_volume() -> Optional[float]:
    """Return the latest BIST100 volume, or None if unavailable."""
    from providers.registry import get_market_provider
    provider = get_market_provider()
    # Extra yfinance-specific method — check for it gracefully
    if hasattr(provider, "fetch_bist100_volume"):
        return provider.fetch_bist100_volume()
    hist = provider.fetch_ohlcv("XU100.IS", period="5d")
    if hist is None or hist.empty:
        return None
    return float(hist["Volume"].iloc[-1])
