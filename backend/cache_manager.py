"""
OptiTrade Cache Manager
=======================
Two-backend, drop-in TTL cache.

Backend selection (at startup, singleton):
  REDIS_URL set  →  RedisCacheManager (recommended for production)
  REDIS_URL unset →  CacheManager     (in-memory, single-process only)

All call sites use the same interface regardless of backend.

Interface
---------
  get(key)               → Any | None
  set(key, value, ttl)   → None
  delete(key)            → bool
  clear(pattern=None)    → int   (keys removed)
  evict_expired()        → int   (no-op for Redis, which manages TTL natively)
  get_stats()            → dict

Serialization (Redis backend)
------------------------------
Pydantic models are serialized via model_dump_json().
Plain dicts / primitives use json.dumps(default=str).
Reads always return the raw dict — FastAPI reconstructs Pydantic models from
dicts transparently when a response_model is declared.
"""
import json
import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── In-memory backend ──────────────────────────────────────────────────────────

class CacheManager:
    """Thread-safe in-memory TTL cache (single-process; not shared across workers)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock  = threading.Lock()
        self._hits  = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            expire_at, value = entry
            if time.monotonic() > expire_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self, pattern: Optional[str] = None) -> int:
        with self._lock:
            if pattern is None:
                count = len(self._store)
                self._store.clear()
                return count
            matching = [k for k in self._store if pattern in k]
            for k in matching:
                del self._store[k]
            return len(matching)

    def evict_expired(self) -> int:
        with self._lock:
            now = time.monotonic()
            expired = [k for k, (exp, _) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]
            return len(expired)

    def get_stats(self) -> dict:
        with self._lock:
            now    = time.monotonic()
            active = sum(1 for exp, _ in self._store.values() if exp > now)
            total  = self._hits + self._misses
            return {
                "backend":      "memory",
                "active_keys":  active,
                "total_keys":   len(self._store),
                "hits":         self._hits,
                "misses":       self._misses,
                "hit_rate_pct": round(self._hits / total * 100, 1) if total else 0.0,
            }


# ── Redis backend ─────────────────────────────────────────────────────────────

class RedisCacheManager:
    """
    Redis-backed cache with the same interface as CacheManager.

    Values are JSON-serialized so they can be inspected with redis-cli.
    Pydantic models are serialized via model_dump_json() so nested objects
    survive the round-trip as plain dicts; FastAPI re-validates them via
    response_model when returning to clients.
    """

    def __init__(self, redis_url: str) -> None:
        import redis as redis_lib
        self._redis = redis_lib.from_url(redis_url, decode_responses=True, socket_timeout=2)
        self._lock  = threading.Lock()
        self._hits  = 0
        self._misses = 0
        self._redis.ping()  # fail fast if Redis is unreachable at startup

    # ── Interface ──────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self._redis.get(key)
        except Exception as exc:
            logger.warning("Redis GET %s failed: %s", key, exc)
            with self._lock:
                self._misses += 1
            return None
        if raw is None:
            with self._lock:
                self._misses += 1
            return None
        with self._lock:
            self._hits += 1
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        try:
            self._redis.setex(key, ttl, _serialize(value))
        except Exception as exc:
            logger.warning("Redis SET %s failed: %s", key, exc)

    def delete(self, key: str) -> bool:
        try:
            return bool(self._redis.delete(key))
        except Exception as exc:
            logger.warning("Redis DELETE %s failed: %s", key, exc)
            return False

    def clear(self, pattern: Optional[str] = None) -> int:
        """Remove keys matching *pattern* (SCAN-based; safe for production)."""
        try:
            match = f"*{pattern}*" if pattern else "*"
            keys: list[str] = []
            cursor = 0
            while True:
                cursor, batch = self._redis.scan(cursor, match=match, count=200)
                keys.extend(batch)
                if cursor == 0:
                    break
            if not keys:
                return 0
            return self._redis.delete(*keys)
        except Exception as exc:
            logger.warning("Redis CLEAR %s failed: %s", pattern, exc)
            return 0

    def evict_expired(self) -> int:
        """No-op: Redis manages key expiry natively via TTL."""
        return 0

    def get_stats(self) -> dict:
        with self._lock:
            hits   = self._hits
            misses = self._misses
        total = hits + misses
        try:
            info = self._redis.info("stats")
            r_hits   = info.get("keyspace_hits",   hits)
            r_misses = info.get("keyspace_misses", misses)
            r_total  = r_hits + r_misses
            hit_rate = round(r_hits / r_total * 100, 1) if r_total else 0.0
            active   = self._redis.dbsize()
        except Exception:
            hit_rate = round(hits / total * 100, 1) if total else 0.0
            active   = -1
        return {
            "backend":      "redis",
            "active_keys":  active,
            "hits":         hits,
            "misses":       misses,
            "hit_rate_pct": hit_rate,
        }


# ── Serialization helpers ─────────────────────────────────────────────────────

def _serialize(value: Any) -> str:
    try:
        from pydantic import BaseModel
        if isinstance(value, BaseModel):
            return value.model_dump_json()
    except ImportError:
        pass
    return json.dumps(value, default=str)


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[Any] = None
_instance_lock = threading.Lock()


def get_cache_manager():
    """
    Return the process-level cache singleton.

    - If REDIS_URL is set and Redis is reachable: RedisCacheManager
    - Otherwise: CacheManager (in-memory fallback)
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = _create_cache()
    return _instance


def _create_cache():
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            manager = RedisCacheManager(redis_url)
            logger.info("Cache backend: Redis (%s).", redis_url)
            return manager
        except Exception as exc:
            logger.warning(
                "Redis unavailable (%s) — falling back to in-memory cache.", exc
            )
    logger.info("Cache backend: in-memory (REDIS_URL not set or Redis unreachable).")
    return CacheManager()


def invalidate_cache(pattern: Optional[str] = None) -> int:
    """Convenience wrapper — invalidate by pattern or clear everything."""
    return get_cache_manager().clear(pattern)


def reset_cache_singleton() -> None:
    """
    Force recreation of the cache singleton.  Used in tests only.
    Never call from production code.
    """
    global _instance
    with _instance_lock:
        _instance = None
