"""OptiTrade Analytics & Dashboard Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class DashboardConfig:
    """Runtime settings for the Analytics & Dashboard Platform."""

    # Redis cache (each dashboard view is cached under its own TTL - these
    # are intentionally short since every view is cheap to recompute from
    # already-persisted data; the cache exists to protect against
    # request bursts, not to serve stale data for long.)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    overview_cache_ttl_seconds: int = 30
    dashboard_cache_ttl_seconds: int = 30

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "optitrade"
    postgres_user: str = "optitrade_user"
    postgres_password: str = ""

    # Market dashboard defaults
    default_market_symbols: tuple = (
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "BTC-USD", "ETH-USD",
    )
    recent_history_limit: int = 50

    @classmethod
    def from_env(cls) -> "DashboardConfig":
        load_dotenv()
        return cls(
            redis_host=os.getenv("DASHBOARD_REDIS_HOST", os.getenv("FEATURE_STORE_REDIS_HOST", "localhost")),
            redis_port=int(os.getenv("DASHBOARD_REDIS_PORT", os.getenv("FEATURE_STORE_REDIS_PORT", "6379"))),
            redis_db=int(os.getenv("DASHBOARD_REDIS_DB", os.getenv("FEATURE_STORE_REDIS_DB", "0"))),
            overview_cache_ttl_seconds=int(os.getenv("DASHBOARD_OVERVIEW_CACHE_TTL_SECONDS", "30")),
            dashboard_cache_ttl_seconds=int(os.getenv("DASHBOARD_CACHE_TTL_SECONDS", "30")),
            postgres_host=os.getenv("FEATURE_STORE_POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("FEATURE_STORE_POSTGRES_PORT", "5432")),
            postgres_db=os.getenv("FEATURE_STORE_POSTGRES_DB", "optitrade"),
            postgres_user=os.getenv("FEATURE_STORE_POSTGRES_USER", "optitrade_user"),
            postgres_password=os.getenv("FEATURE_STORE_POSTGRES_PASSWORD", ""),
            recent_history_limit=int(os.getenv("DASHBOARD_RECENT_HISTORY_LIMIT", "50")),
        )
