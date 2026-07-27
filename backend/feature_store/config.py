"""
OptiTrade Feature Store — configuration.

Reads connection settings from environment variables (loaded via
python-dotenv's `load_dotenv()`, already invoked by `main.py`), with
localhost defaults matching this project's local development setup.
Docker Compose overrides these via `environment:` entries pointing at the
`postgres`/`redis` service names instead (see `docker-compose.yml`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class FeatureStoreConfig:
    """Immutable connection/runtime configuration for the feature store."""

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    redis_host: str
    redis_port: int
    redis_db: int
    online_ttl_seconds: int = 15 * 60

    @classmethod
    def from_env(cls) -> "FeatureStoreConfig":
        # Mirrors the existing convention in test_engine.py/dashboard.py:
        # main.py already calls load_dotenv() once, but this package is
        # also usable standalone (tests, research scripts, future
        # engines), so it loads backend/.env itself too. Idempotent and
        # harmless if the environment is already populated.
        load_dotenv()
        return cls(
            postgres_host=os.getenv("FEATURE_STORE_POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("FEATURE_STORE_POSTGRES_PORT", "5432")),
            postgres_db=os.getenv("FEATURE_STORE_POSTGRES_DB", "optitrade"),
            postgres_user=os.getenv("FEATURE_STORE_POSTGRES_USER", "optitrade_user"),
            postgres_password=os.getenv("FEATURE_STORE_POSTGRES_PASSWORD", ""),
            redis_host=os.getenv("FEATURE_STORE_REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("FEATURE_STORE_REDIS_PORT", "6379")),
            redis_db=int(os.getenv("FEATURE_STORE_REDIS_DB", "0")),
            online_ttl_seconds=int(
                os.getenv("FEATURE_STORE_ONLINE_TTL_SECONDS", str(15 * 60))
            ),
        )
