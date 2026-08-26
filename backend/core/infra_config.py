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
indefinitely (redis-py's own default is to never time out) - and, as of
this module's `redis_retry_disabled()`, the retry policy layered on top
of that timeout: redis-py's own `Redis()` default is NOT "one attempt
bounded by socket_connect_timeout" but up to 10 retries with
exponential+jitter backoff on every `ConnectionError`/`TimeoutError`.
Verified live (production audit E2E chaos test): a genuine connection-
refused failure that a raw socket detects in under a millisecond took
~3.9 seconds through an otherwise-correctly-timeout-configured
`redis.Redis` client - the retry loop, not the timeout, was governing
how long a caller actually waited. Every online-store/cache read this
backend makes is already designed to degrade gracefully on a Redis
failure (fall back to the offline Postgres store, or treat a cache
miss as absent) - that fallback is only as good as how fast the
failure is actually detected, so the retry loop was silently
undermining every one of those existing hardening passes.
"""
from __future__ import annotations

import os
from typing import Tuple

from redis.backoff import NoBackoff
from redis.retry import Retry


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


def postgres_connect_timeout_seconds() -> int:
    """Passed as `connect_timeout` at every `psycopg2.pool.
    ThreadedConnectionPool(...)` construction site in this backend.

    Verified live (production audit E2E chaos test): with no
    `connect_timeout` set (psycopg2's own default - libpq never times
    out a TCP-level connection attempt on its own), a connection
    attempt to an unreachable-but-not-actively-refusing address (a
    network partition, not "the service is down and refusing
    connections" - psycopg2 already fails that case in under a
    millisecond) hung past 20 seconds with no way to bound it. Every
    request this backend serves runs through a bounded thread pool
    (see main.py's `_executor`); one such hang per in-flight Postgres
    connection attempt would exhaust it far faster than any of this
    codebase's existing per-repository failure isolation was ever
    designed to tolerate."""
    return int(os.getenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", "5"))


def redis_retry_disabled() -> Retry:
    """Pass as `retry=` (together with `retry_on_error=[]`) at every
    `redis.Redis(...)` construction site, so a connection failure is
    reported after exactly one attempt, bounded by
    `redis_socket_timeout_seconds()` - see this module's own docstring
    for why redis-py's default retry policy defeats that timeout's
    entire purpose. A fresh `Retry` instance per call: `Retry` objects
    are not documented as safe to share across multiple `redis.Redis`
    clients/connection pools."""
    return Retry(NoBackoff(), 0)


def postgres_pool_size_from_env(package_prefix: str, default_minconn: int, default_maxconn: int) -> Tuple[int, int]:
    """(minconn, maxconn) for `package_prefix`'s `ThreadedConnectionPool`
    (e.g. "USERS", "WATCHLIST") - every production repository previously
    hardcoded these as Python default parameters with no way to tune pool
    size without a code change. Falls back to each repository's own
    existing default (unchanged) when no env var is set, so every current
    deployment behaves identically until an operator opts in."""
    minconn = int(os.getenv(f"{package_prefix}_POSTGRES_POOL_MIN", str(default_minconn)))
    maxconn = int(os.getenv(f"{package_prefix}_POSTGRES_POOL_MAX", str(default_maxconn)))
    return minconn, maxconn
