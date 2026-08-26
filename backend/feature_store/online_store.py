"""
OptiTrade Feature Store — Redis-backed online store.

Holds only the LATEST known value per (symbol, feature_name), for
low-latency reads. Never used for point-in-time/historical queries —
that is exclusively the offline store's job (see `offline_store.py`).
Every value is stored as a JSON-encoded string: Task 3's characterization
of `core/cache_manager.TTLCache` found the in-memory cache pattern that
predates this does no serialization at all (values are shared Python
object references); a network-attached cache genuinely needs to
serialize.

This is a cache, not a source of truth: both `get_latest` and
`set_latest` catch Redis connectivity errors internally, log them, and
degrade gracefully (a failed read is treated as a miss; a failed write is
silently skipped) rather than raising — a Redis outage must never be
allowed to break a caller relying on this as an optimization over the
offline store.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import redis

from core.infra_config import redis_retry_disabled, redis_socket_timeout_seconds
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.config import FeatureStoreConfig
from feature_store.models import FeatureRecord

logger = logging.getLogger(__name__)

_MISS = "miss"


def _redis_key(symbol: str, feature_name: str) -> str:
    return f"feature_store:{symbol}:{feature_name}"


class RedisOnlineStore:
    """Online (low-latency, latest-value-only) feature store backed by Redis."""

    def __init__(
        self,
        config: Optional[FeatureStoreConfig] = None,
        client: Optional["redis.Redis"] = None,
    ) -> None:
        self._config = config or FeatureStoreConfig.from_env()
        timeout = redis_socket_timeout_seconds()
        self._client = client or redis.Redis(
            host=self._config.redis_host,
            port=self._config.redis_port,
            db=self._config.redis_db,
            decode_responses=True,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            retry=redis_retry_disabled(),
            retry_on_error=[],
        )

    def get_latest(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]:
        started_at = time.perf_counter()
        try:
            raw = self._client.get(_redis_key(symbol, feature_name))
        except redis.RedisError as exc:
            log_event(
                logger,
                component="feature_store",
                module="feature_store.online_store",
                operation="get_latest",
                status=STATUS_ERROR,
                symbol=symbol,
                feature_name=feature_name,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.WARNING,
            )
            return None  # treat as a cache miss - caller falls back to the offline store

        log_event(
            logger,
            component="feature_store",
            module="feature_store.online_store",
            operation="get_latest",
            status=STATUS_SUCCESS if raw is not None else _MISS,
            symbol=symbol,
            feature_name=feature_name,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        if raw is None:
            return None
        return FeatureRecord.model_validate_json(raw)

    def set_latest(self, record: FeatureRecord) -> None:
        started_at = time.perf_counter()
        key = _redis_key(record.symbol, record.feature_name)
        try:
            self._client.set(key, record.model_dump_json(), ex=self._config.online_ttl_seconds)
        except redis.RedisError as exc:
            log_event(
                logger,
                component="feature_store",
                module="feature_store.online_store",
                operation="set_latest",
                status=STATUS_ERROR,
                symbol=record.symbol,
                feature_name=record.feature_name,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.WARNING,
            )
            return  # best-effort cache write only - never fails the caller
        log_event(
            logger,
            component="feature_store",
            module="feature_store.online_store",
            operation="set_latest",
            status=STATUS_SUCCESS,
            symbol=record.symbol,
            feature_name=record.feature_name,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )

    def ping(self) -> bool:
        """Connectivity check used by `FeatureStoreService.health_check()`."""
        try:
            return bool(self._client.ping())
        except redis.RedisError:
            return False
