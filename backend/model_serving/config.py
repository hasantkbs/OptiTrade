"""OptiTrade Model Serving Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class ModelServingConfig:
    """Runtime settings for the Model Serving Platform."""

    # Model Cache (Redis-backed metadata cache - never the trainer
    # object itself, which stays in-process; see cache.py)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    cache_ttl_seconds: int = 30

    # Model Loader
    reload_check_interval_seconds: float = 5.0

    # Inference
    max_parallel_workers: int = 8
    async_prediction_timeout_seconds: float = 8.0

    # Shadow inference
    shadow_max_parallel_workers: int = 4

    # Health monitoring
    latency_history_size: int = 200

    engine_version: str = "v1"

    @classmethod
    def from_env(cls) -> "ModelServingConfig":
        load_dotenv()
        return cls(
            redis_host=os.getenv("MODEL_SERVING_REDIS_HOST", os.getenv("FEATURE_STORE_REDIS_HOST", "localhost")),
            redis_port=int(os.getenv("MODEL_SERVING_REDIS_PORT", os.getenv("FEATURE_STORE_REDIS_PORT", "6379"))),
            redis_db=int(os.getenv("MODEL_SERVING_REDIS_DB", os.getenv("FEATURE_STORE_REDIS_DB", "0"))),
            cache_ttl_seconds=int(os.getenv("MODEL_SERVING_CACHE_TTL_SECONDS", "30")),
            reload_check_interval_seconds=float(os.getenv("MODEL_SERVING_RELOAD_CHECK_INTERVAL_SECONDS", "5.0")),
            max_parallel_workers=int(os.getenv("MODEL_SERVING_MAX_PARALLEL_WORKERS", "8")),
            async_prediction_timeout_seconds=float(
                os.getenv("MODEL_SERVING_ASYNC_PREDICTION_TIMEOUT_SECONDS", "8.0")
            ),
            shadow_max_parallel_workers=int(os.getenv("MODEL_SERVING_SHADOW_MAX_PARALLEL_WORKERS", "4")),
            latency_history_size=int(os.getenv("MODEL_SERVING_LATENCY_HISTORY_SIZE", "200")),
            engine_version=os.getenv("MODEL_SERVING_ENGINE_VERSION", "v1"),
        )
