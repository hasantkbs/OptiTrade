"""OptiTrade Pipeline — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class PipelineConfig:
    """Runtime settings for the production execution pipeline."""

    engine_timeout_seconds: float = 8.0
    max_retries: int = 1
    max_parallel_workers: int = 8

    technical_engine_version: str = "v1"
    fundamental_engine_version: str = "v1"
    news_engine_version: str = "v1"

    low_volatility_threshold_pct: float = 10.0
    high_volatility_threshold_pct: float = 25.0

    pipeline_version: str = "v1"

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        load_dotenv()
        return cls(
            engine_timeout_seconds=float(os.getenv("PIPELINE_ENGINE_TIMEOUT_SECONDS", "8.0")),
            max_retries=int(os.getenv("PIPELINE_MAX_RETRIES", "1")),
            max_parallel_workers=int(os.getenv("PIPELINE_MAX_PARALLEL_WORKERS", "8")),
            technical_engine_version=os.getenv("PIPELINE_TECHNICAL_ENGINE_VERSION", "v1"),
            fundamental_engine_version=os.getenv("PIPELINE_FUNDAMENTAL_ENGINE_VERSION", "v1"),
            news_engine_version=os.getenv("PIPELINE_NEWS_ENGINE_VERSION", "v1"),
            low_volatility_threshold_pct=float(os.getenv("PIPELINE_LOW_VOLATILITY_THRESHOLD_PCT", "10.0")),
            high_volatility_threshold_pct=float(os.getenv("PIPELINE_HIGH_VOLATILITY_THRESHOLD_PCT", "25.0")),
            pipeline_version=os.getenv("PIPELINE_VERSION", "v1"),
        )
