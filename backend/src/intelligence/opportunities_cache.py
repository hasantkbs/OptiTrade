"""Redis-backed cache for GET /market/opportunities/{market}.

Scanning a whole market's symbol universe (18-34 symbols through the
full Technical/Fundamental/News pipeline) takes far longer than any
HTTP request should wait, so the real computation happens only in
market_opportunities_refresh_loop (main.py) - this is purely the read/
write side of that cache. Same connection conventions as dashboard/
scheduler.py's own Redis client (retry disabled, bounded socket
timeout); a separate client rather than sharing DashboardScheduler's
because intelligence/ has no existing dependency on it and the two
caches have nothing else in common.
"""
from __future__ import annotations

import logging
from typing import Optional

import redis

from core.infra_config import redis_retry_disabled, redis_settings_from_env, redis_socket_timeout_seconds
from core.structured_logging import STATUS_ERROR, log_event

logger = logging.getLogger(__name__)
_MODULE = "intelligence.opportunities_cache"
_COMPONENT = "intelligence"

_CACHE_KEY_PREFIX = "market:opportunities:"

# Refreshed every 5 minutes (main.py's _MARKET_OPPORTUNITIES_REFRESH_
# INTERVAL_SECONDS); TTL set well past that so a slow or skipped cycle
# (see _HEAVY_BACKGROUND_SCAN_LOCK) doesn't expire the last good result
# out from under the endpoint - same reasoning as dashboard_cache_ttl_
# seconds' own 30s -> 300s bump.
_TTL_SECONDS = 900


class OpportunitiesCache:
    def __init__(self, redis_client: Optional["redis.Redis"] = None, ttl_seconds: int = _TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        if redis_client is not None:
            self._client = redis_client
        else:
            host, port, db = redis_settings_from_env("DASHBOARD")
            timeout = redis_socket_timeout_seconds()
            self._client = redis.Redis(
                host=host, port=port, db=db, decode_responses=True,
                socket_timeout=timeout, socket_connect_timeout=timeout,
                retry=redis_retry_disabled(), retry_on_error=[],
            )

    def set(self, market: str, payload_json: str) -> None:
        try:
            self._client.set(f"{_CACHE_KEY_PREFIX}{market}", payload_json, ex=self._ttl_seconds)
        except redis.RedisError as exc:
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="set", status=STATUS_ERROR,
                error_type=type(exc).__name__, market=market, level=logging.WARNING,
            )

    def get(self, market: str) -> Optional[str]:
        try:
            return self._client.get(f"{_CACHE_KEY_PREFIX}{market}")
        except redis.RedisError as exc:
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="get", status=STATUS_ERROR,
                error_type=type(exc).__name__, market=market, level=logging.WARNING,
            )
            return None
