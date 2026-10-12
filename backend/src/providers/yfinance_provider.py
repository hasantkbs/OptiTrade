"""
OptiTrade — yfinance MarketDataProvider Implementation
=======================================================
Wraps yfinance calls behind the MarketDataProvider Protocol.
This is the sole concrete data provider until Phase 3 (Polygon / Bloomberg).

All methods return None / {} / "Notr" on failure — they never raise.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeoutError
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# yfinance's own `history(..., timeout=10)` default only bounds a single
# HTTP request - an invalid/delisted symbol has been observed taking 30s+
# end to end regardless (internal retry/backoff across several requests
# compounds past that single-request timeout), which is longer than both
# this app's own frontend timeout and nginx's 30s proxy_read_timeout, so
# a typo'd symbol hung instead of failing fast. This wraps each call in
# its own single-use thread so a hard wall-clock deadline applies no
# matter how yfinance internally retries - the thread is abandoned (not
# joined) on a timeout rather than blocked on, matching this app's
# existing "bound the wait, let the orphaned call finish on its own"
# convention (see /quant/analyze's _QUANT_ANALYZE_CACHE).
_FETCH_TIMEOUT_SECONDS = 15


def _call_with_timeout(fn, *args, **kwargs):
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=_FETCH_TIMEOUT_SECONDS)
    finally:
        pool.shutdown(wait=False)


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
            hist   = _call_with_timeout(ticker.history, period=period)
            if hist is None or hist.empty:
                logger.warning("No OHLCV data for %s (period=%s)", symbol, period)
                return None
            return hist
        except _FutureTimeoutError:
            logger.error("yfinance OHLCV fetch timed out for %s after %ss", symbol, _FETCH_TIMEOUT_SECONDS)
            return None
        except Exception as exc:
            logger.error("yfinance OHLCV fetch failed for %s: %s", symbol, exc)
            return None

    def fetch_info(self, symbol: str) -> dict:
        """Return fundamental/metadata dict or empty dict."""
        try:
            info = _call_with_timeout(lambda: yf.Ticker(symbol).info)
            return info or {}
        except _FutureTimeoutError:
            logger.warning("yfinance info fetch timed out for %s after %ss", symbol, _FETCH_TIMEOUT_SECONDS)
            return {}
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
