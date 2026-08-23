"""OptiTrade Model Serving Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from core.infra_config import redis_settings_from_env


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
    # Bounds the in-process `ModelLoader._loaded` cache (loader.py) - an
    # LRU eviction kicks in past this many distinct model_ids, so a long-
    # running process (repeated `load_version_override`/rollback/reload
    # traffic across many model_ids) can't grow that dict unboundedly.
    # 64 comfortably covers "one ACTIVE model per (label, horizon)" across
    # every `LabelName` (7) times a generous horizon count, plus headroom
    # for Research-Lab version-override traffic.
    loader_max_cached_models: int = 64

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
        redis_host, redis_port, redis_db = redis_settings_from_env("MODEL_SERVING")
        return cls(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            cache_ttl_seconds=int(os.getenv("MODEL_SERVING_CACHE_TTL_SECONDS", "30")),
            reload_check_interval_seconds=float(os.getenv("MODEL_SERVING_RELOAD_CHECK_INTERVAL_SECONDS", "5.0")),
            loader_max_cached_models=int(os.getenv("MODEL_SERVING_LOADER_MAX_CACHED_MODELS", "64")),
            max_parallel_workers=int(os.getenv("MODEL_SERVING_MAX_PARALLEL_WORKERS", "8")),
            async_prediction_timeout_seconds=float(
                os.getenv("MODEL_SERVING_ASYNC_PREDICTION_TIMEOUT_SECONDS", "8.0")
            ),
            shadow_max_parallel_workers=int(os.getenv("MODEL_SERVING_SHADOW_MAX_PARALLEL_WORKERS", "4")),
            latency_history_size=int(os.getenv("MODEL_SERVING_LATENCY_HISTORY_SIZE", "200")),
            engine_version=os.getenv("MODEL_SERVING_ENGINE_VERSION", "v1"),
        )
