"""
OptiTrade Model Serving Platform — Redis-backed model metadata cache.

Caches the resolved ACTIVE `ml_training.registry.ModelRegistryEntry`
for each (label_name, horizon_days) pair, with a short TTL - never the
trainer object itself (too large to serialize sensibly, and the
trainer's own in-process cache in `loader.py` is what actually avoids
repeated disk reads). This is what makes "automatic reload"
(requirement 1) and "version routing" (requirement 6) cheap enough to
check on every single prediction: a TTL'd Redis read replaces a
`ml_training.registry` Postgres query on every cache hit, with staleness
bounded by `cache_ttl_seconds` - a newly-promoted model is picked up
within one TTL window with no explicit invalidation required, and
`invalidate`/`invalidate_all` exist for the rare case a caller (e.g. a
rollback) needs it to happen immediately instead.

Mirrors `feature_store.online_store.RedisOnlineStore`'s exact
degrade-gracefully-on-Redis-failure contract: a cache miss (including a
connectivity failure) is never raised to the caller, which simply falls
back to resolving the ACTIVE entry straight from `ml_training.registry`
instead.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

import redis

from core.infra_config import redis_retry_disabled, redis_socket_timeout_seconds
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from ml_training.models import LabelName, ModelRegistryEntry
from model_serving.config import ModelServingConfig

logger = logging.getLogger(__name__)

_KEY_PREFIX = "model_serving:active"
_MISS = "miss"


def _redis_key(label_name: LabelName, horizon_days: int) -> str:
    return f"{_KEY_PREFIX}:{label_name.value}:{horizon_days}"


class ModelMetadataCache:
    def __init__(
        self,
        config: Optional[ModelServingConfig] = None,
        client: Optional["redis.Redis"] = None,
    ) -> None:
        self.config = config or ModelServingConfig.from_env()
        timeout = redis_socket_timeout_seconds()
        self._client = client or redis.Redis(
            host=self.config.redis_host, port=self.config.redis_port,
            db=self.config.redis_db, decode_responses=True,
            socket_timeout=timeout, socket_connect_timeout=timeout,
            retry=redis_retry_disabled(), retry_on_error=[],
        )

    def get_active_entry(self, label_name: LabelName, horizon_days: int) -> Optional[ModelRegistryEntry]:
        started_at = time.perf_counter()
        try:
            raw = self._client.get(_redis_key(label_name, horizon_days))
        except redis.RedisError as exc:
            log_event(
                logger, component="model_serving", module="model_serving.cache", operation="get_active_entry",
                status=STATUS_ERROR, label_name=label_name.value, horizon_days=horizon_days,
                error_type=type(exc).__name__, execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.WARNING,
            )
            return None
        log_event(
            logger, component="model_serving", module="model_serving.cache", operation="get_active_entry",
            status=STATUS_SUCCESS if raw is not None else _MISS, label_name=label_name.value,
            horizon_days=horizon_days, execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return ModelRegistryEntry.model_validate_json(raw) if raw is not None else None

    def set_active_entry(self, label_name: LabelName, horizon_days: int, entry: ModelRegistryEntry) -> None:
        started_at = time.perf_counter()
        try:
            self._client.set(
                _redis_key(label_name, horizon_days), entry.model_dump_json(), ex=self.config.cache_ttl_seconds,
            )
        except redis.RedisError as exc:
            log_event(
                logger, component="model_serving", module="model_serving.cache", operation="set_active_entry",
                status=STATUS_ERROR, label_name=label_name.value, horizon_days=horizon_days,
                error_type=type(exc).__name__, execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.WARNING,
            )
            return
        log_event(
            logger, component="model_serving", module="model_serving.cache", operation="set_active_entry",
            status=STATUS_SUCCESS, label_name=label_name.value, horizon_days=horizon_days,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )

    def invalidate(self, label_name: LabelName, horizon_days: int) -> None:
        try:
            self._client.delete(_redis_key(label_name, horizon_days))
        except redis.RedisError as exc:
            log_event(
                logger, component="model_serving", module="model_serving.cache", operation="invalidate",
                status=STATUS_ERROR, label_name=label_name.value, horizon_days=horizon_days,
                error_type=type(exc).__name__, level=logging.WARNING,
            )

    def invalidate_all(self) -> None:
        try:
            keys: List[str] = list(self._client.scan_iter(match=f"{_KEY_PREFIX}:*"))
            if keys:
                self._client.delete(*keys)
        except redis.RedisError as exc:
            log_event(
                logger, component="model_serving", module="model_serving.cache", operation="invalidate_all",
                status=STATUS_ERROR, error_type=type(exc).__name__, level=logging.WARNING,
            )

    def ping(self) -> Tuple[bool, Optional[float]]:
        """Connectivity check used by `health.py`. Returns
        `(healthy, latency_ms)` - `latency_ms` is `None` when the ping
        itself failed."""
        started_at = time.perf_counter()
        try:
            healthy = bool(self._client.ping())
        except redis.RedisError:
            return False, None
        return healthy, (time.perf_counter() - started_at) * 1000
