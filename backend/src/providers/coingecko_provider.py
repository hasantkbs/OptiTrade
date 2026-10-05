"""
OptiTrade — CoinGecko BTC dominance provider
================================================
Calls CoinGecko's free, keyless /api/v3/global endpoint for BTC's
share of total crypto market cap. Mirrors BinanceProvider's own
"return None on any failure, never raise" convention
(providers/binance_provider.py) - this is an optional market-context
figure for the simplified home page, never a value any decision logic
depends on.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"


def get_btc_dominance() -> Optional[float]:
    """BTC's percentage share of total crypto market cap, or None on
    any failure (timeout, non-200, missing field) - logged, never
    raised."""
    try:
        resp = httpx.get(_GLOBAL_URL, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        value = data["data"]["market_cap_percentage"]["btc"]
        return float(value)
    except Exception as exc:
        logger.warning("CoinGecko BTC dominance fetch failed: %s", exc)
        return None
