"""
OptiTrade Model Serving Platform — Health Monitoring.

Requirement 7: model health, inference latency, cache health, and
loading failures, all as one structured `ServingHealthReport`
(`models.py`) rather than ad-hoc log lines - a caller (a `/health`-style
endpoint, or an ops dashboard) gets one call that answers "is serving
actually working."
"""
from __future__ import annotations

import statistics
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Optional

from model_serving.cache import ModelMetadataCache
from model_serving.config import ModelServingConfig
from model_serving.loader import ModelLoader
from model_serving.models import (
    CacheHealthStatus,
    InferenceLatencyStats,
    ModelHealthStatus,
    ServingHealthReport,
)


class HealthMonitor:
    def __init__(
        self,
        loader: ModelLoader,
        cache: ModelMetadataCache,
        config: Optional[ModelServingConfig] = None,
    ) -> None:
        self.config = config or ModelServingConfig.from_env()
        self.loader = loader
        self.cache = cache
        self._latencies_ms: Deque[float] = deque(maxlen=self.config.latency_history_size)

    def record_latency(self, duration_ms: float) -> None:
        self._latencies_ms.append(duration_ms)

    def latency_stats(self) -> InferenceLatencyStats:
        if not self._latencies_ms:
            return InferenceLatencyStats(sample_count=0)
        samples = sorted(self._latencies_ms)
        return InferenceLatencyStats(
            sample_count=len(samples),
            avg_ms=statistics.fmean(samples),
            p50_ms=_percentile(samples, 0.50),
            p95_ms=_percentile(samples, 0.95),
        )

    def model_health(self) -> list:
        now = datetime.now(timezone.utc)
        statuses = []
        for model_id, loaded_model in self.loader.loaded_models().items():
            age_seconds = (now - loaded_model.loaded_at).total_seconds()
            statuses.append(
                ModelHealthStatus(
                    model_id=model_id, loaded=True, loaded_at=loaded_model.loaded_at,
                    stale=age_seconds > self.config.cache_ttl_seconds,
                    last_error=self.loader.last_load_error(model_id),
                )
            )
        return statuses

    def cache_health(self) -> CacheHealthStatus:
        healthy, latency_ms = self.cache.ping()
        return CacheHealthStatus(healthy=healthy, latency_ms=latency_ms, error=None if healthy else "ping failed")

    def report(self) -> ServingHealthReport:
        return ServingHealthReport(
            cache=self.cache_health(), models=self.model_health(), inference_latency=self.latency_stats(),
            loading_failure_count=self.loader.loading_failure_count,
        )


def _percentile(sorted_samples: list, fraction: float) -> float:
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    index = min(len(sorted_samples) - 1, int(round(fraction * (len(sorted_samples) - 1))))
    return sorted_samples[index]
