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


# SERVER STEP 1 (deployment prep): arbitrary but fixed pg_advisory_lock key
# for `acquire_scheduler_leader_lock()` below. Any int64 works - it only
# has to be stable across deploys and not collide with another advisory
# lock this codebase takes (there are none today).
_SCHEDULER_LEADER_LOCK_KEY = 727001

_scheduler_leader_lock_conn = None  # type: ignore[var-annotated]


def acquire_scheduler_leader_lock() -> bool:
    """True if this process should run the singleton background loops
    started once in `main.py`'s `startup_event` (self-evolution retrain,
    alert scan, paper-trading fill, retention purge).

    Production runs `uvicorn --workers N` (N>1, see Dockerfile/
    UVICORN_WORKERS) - N independent OS processes, each executing its
    own copy of `startup_event`. Left ungated, that means N copies of a
    *daily model retrain* and N copies of every periodic scan/fill loop
    running concurrently - the exact "background jobs must not
    accidentally start multiple times merely because multiple API
    workers exist" hazard.

    PostgreSQL's session-scoped `pg_try_advisory_lock` makes exactly one
    worker "win": it never blocks, returns true to the first caller and
    false to every other caller for as long as the first caller's
    connection stays open, and releases automatically if that process
    (and its connection) dies - no separate scheduler process, extra
    dependency, or new coordination service required, and nothing here
    changes what the loops themselves do.

    Fails open (returns True) if PostgreSQL can't be reached at all, so
    a single-worker/local-dev run (the common case where duplication
    cannot happen) keeps working exactly as before; only a real
    multi-worker deployment with a reachable database benefits from the
    dedup, matching this module's existing fall-back-to-current-
    behavior convention."""
    global _scheduler_leader_lock_conn
    try:
        import psycopg2

        host, port, db, user, password = postgres_settings_from_env()
        conn = psycopg2.connect(
            host=host, port=port, dbname=db, user=user, password=password,
            connect_timeout=postgres_connect_timeout_seconds(),
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (_SCHEDULER_LEADER_LOCK_KEY,))
            acquired = bool(cur.fetchone()[0])
        if acquired:
            _scheduler_leader_lock_conn = conn  # held open deliberately - see docstring
        else:
            conn.close()
        return acquired
    except Exception:
        return True


def release_scheduler_leader_lock() -> None:
    """Releases the lock taken by `acquire_scheduler_leader_lock()`, if
    this process is the one holding it. Call during application
    shutdown so a restart (or, in tests, the next FastAPI app instance
    started in the same process) doesn't have to wait for this
    connection to be reaped before another worker can become leader."""
    global _scheduler_leader_lock_conn
    if _scheduler_leader_lock_conn is not None:
        try:
            _scheduler_leader_lock_conn.close()
        except Exception:
            pass
        _scheduler_leader_lock_conn = None
