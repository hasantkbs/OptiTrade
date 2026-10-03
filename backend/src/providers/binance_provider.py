"""
OptiTrade — Binance MarketDataProvider Implementation
=======================================================
Wraps Binance's public REST API (no API key required) behind the
MarketDataProvider Protocol. Used for crypto symbols in HybridProvider —
Binance's klines endpoint is far more reliable than yfinance for crypto
OHLCV and has generous free rate limits.

All methods return None / {} / "Notr" on failure — they never raise.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.binance.com/api/v3"

# iOS/backend crypto symbols use the "-USD" convention (e.g. "BTC-USD").
# Binance trades against USDT, not literal USD, so map the quote asset.
_QUOTE_MAP = {"USD": "USDT"}

_PERIOD_TO_KLINES = {
    "5d":  ("1h", 120),
    "1mo": ("1d", 30),
    "3mo": ("1d", 90),
    "6mo": ("1d", 180),
    "1y":  ("1d", 365),
}


def _to_binance_symbol(symbol: str) -> str:
    """'BTC-USD' -> 'BTCUSDT', 'ETH-USD' -> 'ETHUSDT'."""
    base, _, quote = symbol.upper().partition("-")
    quote = _QUOTE_MAP.get(quote, quote or "USDT")
    return f"{base}{quote}"


class BinanceProvider:
    """Satisfies the MarketDataProvider Protocol using Binance's public API."""

    def fetch_ohlcv(self, symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
        interval, limit = _PERIOD_TO_KLINES.get(period, ("1d", 180))
        pair = _to_binance_symbol(symbol)
        try:
            resp = httpx.get(
                f"{_BASE_URL}/klines",
                params={"symbol": pair, "interval": interval, "limit": limit},
                timeout=10.0,
            )
            resp.raise_for_status()
            raw = resp.json()
            if not raw:
                logger.warning("No Binance OHLCV data for %s (%s)", symbol, pair)
                return None

            df = pd.DataFrame(raw, columns=[
                "open_time", "Open", "High", "Low", "Close", "Volume",
                "close_time", "quote_volume", "trades",
                "taker_base", "taker_quote", "ignore",
            ])
            df[["Open", "High", "Low", "Close", "Volume"]] = df[
                ["Open", "High", "Low", "Close", "Volume"]
            ].astype(float)
            df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as exc:
            logger.error("Binance OHLCV fetch failed for %s (%s): %s", symbol, pair, exc)
            return None

    def fetch_ohlcv_range(self, symbol: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        """Date-bounded daily OHLCV via Binance's startTime/endTime klines
        params - NOT exposed by fetch_ohlcv above (period-only, capped at
        365 daily candles via _PERIOD_TO_KLINES). Used by the historical
        Feature Store backfill, which needs ~2 years of crypto history
        from the SAME source (Binance) the live engine reads for these
        symbols, not yfinance - reuses _to_binance_symbol so symbol
        mapping stays identical to the live fetch_ohlcv path above.
        Binance's klines endpoint allows up to 1000 candles per request;
        1000 daily candles covers ~2.7 years, comfortably enough for this
        backfill's typical ~730-day window in a single call."""
        pair = _to_binance_symbol(symbol)
        try:
            resp = httpx.get(
                f"{_BASE_URL}/klines",
                params={
                    "symbol": pair, "interval": "1d",
                    "startTime": int(start.timestamp() * 1000),
                    "endTime": int(end.timestamp() * 1000),
                    "limit": 1000,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            raw = resp.json()
            if not raw:
                logger.warning("No Binance OHLCV range data for %s (%s)", symbol, pair)
                return None

            df = pd.DataFrame(raw, columns=[
                "open_time", "Open", "High", "Low", "Close", "Volume",
                "close_time", "quote_volume", "trades",
                "taker_base", "taker_quote", "ignore",
            ])
            df[["Open", "High", "Low", "Close", "Volume"]] = df[
                ["Open", "High", "Low", "Close", "Volume"]
            ].astype(float)
            df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as exc:
            logger.error("Binance OHLCV range fetch failed for %s (%s): %s", symbol, pair, exc)
            return None

    def fetch_info(self, symbol: str) -> dict:
        pair = _to_binance_symbol(symbol)
        try:
            resp = httpx.get(
                f"{_BASE_URL}/ticker/24hr", params={"symbol": pair}, timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "regularMarketPrice": float(data.get("lastPrice", 0)) or None,
                "priceChangePercent": float(data.get("priceChangePercent", 0)),
                "volume24h": float(data.get("volume", 0)),
                "high24h": float(data.get("highPrice", 0)),
                "low24h": float(data.get("lowPrice", 0)),
            }
        except Exception as exc:
            logger.warning("Binance info fetch failed for %s (%s): %s", symbol, pair, exc)
            return {}

    def get_balance_status(self, symbol: str) -> str:
        # Crypto has no EPS/balance-sheet concept — always neutral.
        return "Notr"
