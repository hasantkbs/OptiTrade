"""
OptiTrade — Finnhub MarketDataProvider Implementation
=======================================================
Wraps Finnhub's REST API behind the MarketDataProvider Protocol. Used for
US-listed symbols in HybridProvider — Finnhub's free tier (60 calls/min)
is more generous and reliable than yfinance's unofficial rate limits.

Requires the FINNHUB_API_KEY env var. If it's not set, every method
degrades to its "no data" return value (None / {} / "Notr") so the
HybridProvider can transparently fall back to yfinance — it never raises.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"

_PERIOD_TO_DAYS = {
    "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365,
}

_warned_missing_key = False


def _api_key() -> Optional[str]:
    global _warned_missing_key
    key = os.getenv("FINNHUB_API_KEY")
    if not key and not _warned_missing_key:
        logger.warning("FINNHUB_API_KEY not set — FinnhubProvider will return no data.")
        _warned_missing_key = True
    return key or None


class FinnhubProvider:
    """Satisfies the MarketDataProvider Protocol using the Finnhub API."""

    def fetch_ohlcv(self, symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
        key = _api_key()
        if not key:
            return None
        days = _PERIOD_TO_DAYS.get(period, 180)
        now = int(time.time())
        start = now - days * 86400
        try:
            resp = httpx.get(
                f"{_BASE_URL}/stock/candle",
                params={
                    "symbol": symbol.upper(), "resolution": "D",
                    "from": start, "to": now, "token": key,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("s") != "ok" or not data.get("t"):
                logger.warning("No Finnhub OHLCV data for %s (status=%s)", symbol, data.get("s"))
                return None
            df = pd.DataFrame({
                "Open": data["o"], "High": data["h"], "Low": data["l"],
                "Close": data["c"], "Volume": data["v"],
            })
            df.index = pd.to_datetime(data["t"], unit="s", utc=True)
            return df
        except Exception as exc:
            logger.error("Finnhub OHLCV fetch failed for %s: %s", symbol, exc)
            return None

    def fetch_info(self, symbol: str) -> dict:
        key = _api_key()
        if not key:
            return {}
        try:
            resp = httpx.get(
                f"{_BASE_URL}/stock/profile2",
                params={"symbol": symbol.upper(), "token": key},
                timeout=10.0,
            )
            resp.raise_for_status()
            profile = resp.json() or {}
            if not profile:
                return {}
            return {
                "longName":            profile.get("name"),
                "sector":              profile.get("finnhubIndustry"),
                "regularMarketPrice":  None,
                "marketCap":           profile.get("marketCapitalization"),
                "currency":            profile.get("currency"),
                "website":             profile.get("weburl"),
            }
        except Exception as exc:
            logger.warning("Finnhub info fetch failed for %s: %s", symbol, exc)
            return {}

    def get_balance_status(self, symbol: str) -> str:
        key = _api_key()
        if not key:
            return "Notr"
        try:
            resp = httpx.get(
                f"{_BASE_URL}/stock/metric",
                params={"symbol": symbol.upper(), "metric": "all", "token": key},
                timeout=10.0,
            )
            resp.raise_for_status()
            metrics = (resp.json() or {}).get("metric", {})
            fwd = metrics.get("epsForward")
            trl = metrics.get("epsTTM") or metrics.get("epsBasicExclExtraItemsTTM")
            if fwd is None or trl is None:
                return "Notr"
            return "Pozitif" if fwd > trl else "Negatif"
        except Exception:
            return "Notr"
