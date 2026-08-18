"""OptiTrade Analytics & Dashboard Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from core.infra_config import postgres_settings_from_env, redis_settings_from_env


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
        redis_host, redis_port, redis_db = redis_settings_from_env("DASHBOARD")
        postgres_host, postgres_port, postgres_db, postgres_user, postgres_password = postgres_settings_from_env()
        return cls(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            overview_cache_ttl_seconds=int(os.getenv("DASHBOARD_OVERVIEW_CACHE_TTL_SECONDS", "30")),
            dashboard_cache_ttl_seconds=int(os.getenv("DASHBOARD_CACHE_TTL_SECONDS", "30")),
            postgres_host=postgres_host,
            postgres_port=postgres_port,
            postgres_db=postgres_db,
            postgres_user=postgres_user,
            postgres_password=postgres_password,
            recent_history_limit=int(os.getenv("DASHBOARD_RECENT_HISTORY_LIMIT", "50")),
        )
