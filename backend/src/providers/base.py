"""
OptiTrade — Provider Protocols
================================
Every external dependency is hidden behind a typed Protocol.
Business logic depends on the Protocol, never on a concrete SDK.

To add a new data source (Polygon, Bloomberg, Alpha Vantage…):
  1. Create a class that satisfies MarketDataProvider
  2. Register it in providers/registry.py
  3. No other changes needed

MarketDataProvider:
  - fetch_ohlcv(symbol, period) → DataFrame | None
  - fetch_info(symbol) → dict
  - get_balance_status(symbol) → "Pozitif" | "Notr" | "Negatif"
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class MarketDataProvider(Protocol):
    """
    Minimal interface for a market data source.

    Implementations must be stateless with respect to symbol data
    (each call fetches fresh data). Caching lives in the service layer,
    not here.
    """

    def fetch_ohlcv(
        self,
        symbol: str,
        period: str = "6mo",
    ) -> Optional[pd.DataFrame]:
        """
        Return OHLCV DataFrame with columns: Open, High, Low, Close, Volume.
        Index is a DatetimeIndex (UTC).
        Returns None if the symbol is unknown or no data is available.
        """
        ...

    def fetch_info(self, symbol: str) -> dict:
        """
        Return a dict of fundamental / metadata fields.
        Keys vary by provider; callers must use .get() with defaults.
        Returns {} on failure — never raises.
        """
        ...

    def get_balance_status(self, symbol: str) -> str:
        """
        Fundamental balance check.
        Returns: "Pozitif" | "Negatif" | "Notr"
        "Notr" is the safe default when data is unavailable.
        """
        ...
