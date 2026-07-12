"""
OptiTrade — yfinance MarketDataProvider Implementation
=======================================================
Wraps yfinance calls behind the MarketDataProvider Protocol.
This is the sole concrete data provider until Phase 3 (Polygon / Bloomberg).

All methods return None / {} / "Notr" on failure — they never raise.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class YFinanceProvider:
    """
    Satisfies the MarketDataProvider Protocol using yfinance.

    Thread-safe: yfinance.Ticker() is re-created per call so there
    is no shared mutable state.
    """

    # ── MarketDataProvider interface ─────────────────────────────────────────

    def fetch_ohlcv(self, symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
        """Return OHLCV DataFrame or None."""
        try:
            ticker = yf.Ticker(symbol)
            hist   = ticker.history(period=period)
            if hist is None or hist.empty:
                logger.warning("No OHLCV data for %s (period=%s)", symbol, period)
                return None
            return hist
        except Exception as exc:
            logger.error("yfinance OHLCV fetch failed for %s: %s", symbol, exc)
            return None

    def fetch_info(self, symbol: str) -> dict:
        """Return fundamental/metadata dict or empty dict."""
        try:
            info = yf.Ticker(symbol).info
            return info or {}
        except Exception as exc:
            logger.warning("yfinance info fetch failed for %s: %s", symbol, exc)
            return {}

    def get_balance_status(self, symbol: str) -> str:
        """
        Compare forwardEPS vs trailingEPS.
        Returns "Pozitif" | "Negatif" | "Notr"
        """
        try:
            info = self.fetch_info(symbol)
            fwd  = info.get("forwardEps")
            trl  = info.get("trailingEps")
            if fwd is None or trl is None:
                return "Notr"
            return "Pozitif" if fwd > trl else "Negatif"
        except Exception:
            return "Notr"

    # ── Extra helpers (not in Protocol, yfinance-specific) ───────────────────

    def fetch_bist100_volume(self) -> Optional[float]:
        """Convenience: current BIST100 index volume."""
        hist = self.fetch_ohlcv("XU100.IS", period="5d")
        if hist is None or hist.empty:
            return None
        return float(hist["Volume"].iloc[-1])
