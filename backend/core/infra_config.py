"""
OptiTrade — shared Redis/PostgreSQL environment-variable resolution.

Every package's own Config.from_env() (feature_store, portfolio, users,
watchlist, paper_trading, dashboard, model_serving) independently
implemented the identical "PACKAGE_REDIS_HOST env var, falling back to
FEATURE_STORE_REDIS_HOST, falling back to a hardcoded localhost
default" chain for Redis, and the identical "read FEATURE_STORE_POSTGRES_*
directly" resolution for PostgreSQL (every package that touches Postgres
uses the same physical database the Feature Store does - there is,
deliberately, no per-package override chain for that, unlike Redis,
which a package may reasonably want pointed elsewhere). This module
gives every package's from_env() one place to call instead of repeating
that chain - env var names, precedence, and defaults are unchanged for
every existing deployment.

Also centralizes the Redis client socket timeout - previously absent
from every `redis.Redis(...)` construction site in this backend, which
meant a hung/unresponsive Redis server could block a request
indefinitely (redis-py's own default is to never time out).
"""
from __future__ import annotations

import os
from typing import Tuple


def redis_settings_from_env(package_prefix: str, default_db: str = "0") -> Tuple[str, int, int]:
    """(host, port, db) for `package_prefix` (e.g. "PORTFOLIO"),
    falling back to the shared Feature Store Redis settings, falling
    back to a hardcoded localhost default - identical precedence to
    what every caller previously duplicated inline."""
    host = os.getenv(f"{package_prefix}_REDIS_HOST", os.getenv("FEATURE_STORE_REDIS_HOST", "localhost"))
    port = int(os.getenv(f"{package_prefix}_REDIS_PORT", os.getenv("FEATURE_STORE_REDIS_PORT", "6379")))
    db = int(os.getenv(f"{package_prefix}_REDIS_DB", os.getenv("FEATURE_STORE_REDIS_DB", default_db)))
    return host, port, db


def postgres_settings_from_env() -> Tuple[str, int, str, str, str]:
    """(host, port, db, user, password) - the one physical PostgreSQL
    database every package that persists data shares with the Feature
    Store."""
    host = os.getenv("FEATURE_STORE_POSTGRES_HOST", "localhost")
    port = int(os.getenv("FEATURE_STORE_POSTGRES_PORT", "5432"))
    db = os.getenv("FEATURE_STORE_POSTGRES_DB", "optitrade")
    user = os.getenv("FEATURE_STORE_POSTGRES_USER", "optitrade_user")
    password = os.getenv("FEATURE_STORE_POSTGRES_PASSWORD", "")
    return host, port, db, user, password


def redis_socket_timeout_seconds() -> float:
    """Applied as both `socket_timeout` and `socket_connect_timeout` at
    every `redis.Redis(...)` construction site in this backend."""
    return float(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "5"))
