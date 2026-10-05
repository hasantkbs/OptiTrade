"""
OptiTrade — CoinGecko BTC dominance provider
================================================
Calls CoinGecko's free, keyless /api/v3/global endpoint for BTC's
share of total crypto market cap. Mirrors BinanceProvider's own
"return None on any failure, never raise" convention
(providers/binance_provider.py) - this is an optional market-context
figure for the simplified home page, never a value any decision logic
depends on.

A 90-second in-process TTL cache avoids hitting CoinGecko's free-tier
rate limit (roughly 10-30 calls/minute, shared across every consumer
of this process's IP) on every /market/snapshot request - this is a
single shared figure for the whole home page, not a per-user value,
so a short cache has no staleness cost worth the extra outbound calls
it would otherwise cause.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
_CACHE_TTL_SECONDS = 90.0

_cached_value: Optional[float] = None
_cached_at: float = 0.0


def get_btc_dominance() -> Optional[float]:
    """BTC's percentage share of total crypto market cap, or None on
    any failure (timeout, non-200, missing field) - logged, never
    raised. Cached for _CACHE_TTL_SECONDS to avoid hitting CoinGecko's
    rate limit on every request."""
    global _cached_value, _cached_at
    now = time.monotonic()
    if now - _cached_at < _CACHE_TTL_SECONDS:
        return _cached_value

    try:
        resp = httpx.get(_GLOBAL_URL, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        value = data["data"]["market_cap_percentage"]["btc"]
        _cached_value = float(value)
        _cached_at = now
        return _cached_value
    except Exception as exc:
        logger.warning("CoinGecko BTC dominance fetch failed: %s", exc)
        # Do NOT update _cached_at on failure - a transient failure must
        # not lock in a None result for the full TTL window; the next
        # call retries immediately.
        return None
