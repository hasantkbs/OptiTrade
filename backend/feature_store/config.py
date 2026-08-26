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

from core.infra_config import postgres_settings_from_env, redis_settings_from_env


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
        postgres_host, postgres_port, postgres_db, postgres_user, postgres_password = postgres_settings_from_env()
        # "FEATURE_STORE" as its own prefix here just reduces to reading
        # FEATURE_STORE_REDIS_* directly - this package IS the shared
        # Redis settings' source, so there's no separate override tier.
        redis_host, redis_port, redis_db = redis_settings_from_env("FEATURE_STORE")
        return cls(
            postgres_host=postgres_host,
            postgres_port=postgres_port,
            postgres_db=postgres_db,
            postgres_user=postgres_user,
            postgres_password=postgres_password,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            online_ttl_seconds=int(
                os.getenv("FEATURE_STORE_ONLINE_TTL_SECONDS", str(15 * 60))
            ),
        )
