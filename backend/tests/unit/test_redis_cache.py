"""
Unit tests for RedisCacheManager.

All tests mock the underlying redis client — no live Redis required.
Tests verify:
  - get/set/delete/clear/get_stats behave correctly via mock
  - JSON serialization round-trip
  - Pydantic model serialization
  - Graceful error handling (Redis failures return safe defaults)
  - Factory falls back to in-memory when REDIS_URL is not set
"""
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from unittest.mock import MagicMock, patch

from cache_manager import (
    CacheManager, RedisCacheManager, _serialize, get_cache_manager,
    reset_cache_singleton,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_redis():
    r = MagicMock()
    r.ping.return_value = True
    return r


def _redis_cache(mock_r=None):
    """Build a RedisCacheManager with an injected mock redis client."""
    if mock_r is None:
        mock_r = _mock_redis()
    with patch("redis.from_url", return_value=mock_r):
        mgr = RedisCacheManager("redis://localhost:6379/0")
    return mgr, mock_r


# ── Serialization ─────────────────────────────────────────────────────────────

class TestSerialize:
    def test_plain_dict(self):
        out = _serialize({"key": "value", "n": 42})
        assert json.loads(out) == {"key": "value", "n": 42}

    def test_list(self):
        out = _serialize([1, 2, 3])
        assert json.loads(out) == [1, 2, 3]

    def test_pydantic_model(self):
        from pydantic import BaseModel
        class _M(BaseModel):
            x: int
            y: str
        out = _serialize(_M(x=1, y="hello"))
        parsed = json.loads(out)
        assert parsed["x"] == 1
        assert parsed["y"] == "hello"

    def test_non_serializable_fallback_to_str(self):
        # Values that aren't JSON-native should be stringified via default=str
        out = _serialize({"ts": object()})
        assert isinstance(json.loads(out)["ts"], str)


# ── RedisCacheManager ─────────────────────────────────────────────────────────

class TestRedisCacheManagerGet:
    def test_returns_none_on_miss(self):
        mgr, r = _redis_cache()
        r.get.return_value = None
        result = mgr.get("missing")
        assert result is None

    def test_returns_dict_on_hit(self):
        mgr, r = _redis_cache()
        r.get.return_value = json.dumps({"score": 75})
        result = mgr.get("my_key")
        assert result == {"score": 75}

    def test_increments_hits_on_cache_hit(self):
        mgr, r = _redis_cache()
        r.get.return_value = json.dumps({"x": 1})
        mgr.get("k")
        assert mgr._hits == 1
        assert mgr._misses == 0

    def test_increments_misses_on_cache_miss(self):
        mgr, r = _redis_cache()
        r.get.return_value = None
        mgr.get("k")
        assert mgr._misses == 1
        assert mgr._hits == 0

    def test_returns_none_on_redis_error(self):
        mgr, r = _redis_cache()
        r.get.side_effect = Exception("connection refused")
        result = mgr.get("k")
        assert result is None
        assert mgr._misses == 1


class TestRedisCacheManagerSet:
    def test_calls_setex_with_ttl(self):
        mgr, r = _redis_cache()
        mgr.set("mykey", {"data": 1}, ttl=60)
        r.setex.assert_called_once()
        args = r.setex.call_args[0]
        assert args[0] == "mykey"
        assert args[1] == 60

    def test_silently_ignores_redis_error(self):
        mgr, r = _redis_cache()
        r.setex.side_effect = Exception("network error")
        mgr.set("key", {"v": 1}, ttl=30)  # Should not raise

    def test_default_ttl_is_300(self):
        mgr, r = _redis_cache()
        mgr.set("k", "v")
        args = r.setex.call_args[0]
        assert args[1] == 300


class TestRedisCacheManagerDelete:
    def test_returns_true_when_key_deleted(self):
        mgr, r = _redis_cache()
        r.delete.return_value = 1
        assert mgr.delete("k") is True

    def test_returns_false_when_key_missing(self):
        mgr, r = _redis_cache()
        r.delete.return_value = 0
        assert mgr.delete("k") is False

    def test_returns_false_on_redis_error(self):
        mgr, r = _redis_cache()
        r.delete.side_effect = Exception("timeout")
        assert mgr.delete("k") is False


class TestRedisCacheManagerClear:
    def test_uses_scan_not_keys(self):
        """Verify we use SCAN (safe) not KEYS (blocking)."""
        mgr, r = _redis_cache()
        r.scan.return_value = (0, ["scan_bist", "scan_crypto"])
        r.delete.return_value = 2
        count = mgr.clear()
        r.scan.assert_called()
        assert count == 2

    def test_returns_zero_when_no_keys(self):
        mgr, r = _redis_cache()
        r.scan.return_value = (0, [])
        assert mgr.clear() == 0

    def test_pattern_is_passed_to_scan(self):
        mgr, r = _redis_cache()
        r.scan.return_value = (0, ["scan_bist"])
        r.delete.return_value = 1
        mgr.clear("scan")
        call_kwargs = r.scan.call_args[1]
        assert "scan" in call_kwargs.get("match", "")

    def test_returns_zero_on_redis_error(self):
        mgr, r = _redis_cache()
        r.scan.side_effect = Exception("connection error")
        assert mgr.clear() == 0


class TestRedisCacheManagerEvictExpired:
    def test_is_noop_and_returns_zero(self):
        mgr, _ = _redis_cache()
        assert mgr.evict_expired() == 0


class TestRedisCacheManagerStats:
    def test_backend_field_is_redis(self):
        mgr, r = _redis_cache()
        r.info.return_value = {"keyspace_hits": 10, "keyspace_misses": 5}
        r.dbsize.return_value = 42
        stats = mgr.get_stats()
        assert stats["backend"] == "redis"

    def test_includes_active_keys(self):
        mgr, r = _redis_cache()
        r.info.return_value = {"keyspace_hits": 0, "keyspace_misses": 0}
        r.dbsize.return_value = 7
        stats = mgr.get_stats()
        assert stats["active_keys"] == 7

    def test_fallback_on_info_error(self):
        mgr, r = _redis_cache()
        r.info.side_effect = Exception("timeout")
        stats = mgr.get_stats()
        assert "hit_rate_pct" in stats


# ── Factory (get_cache_manager) ───────────────────────────────────────────────

class TestCacheManagerFactory:
    def setup_method(self):
        reset_cache_singleton()

    def teardown_method(self):
        reset_cache_singleton()

    def test_returns_in_memory_when_no_redis_url(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            mgr = get_cache_manager()
        assert isinstance(mgr, CacheManager)

    def test_returns_redis_when_redis_url_set_and_reachable(self):
        mock_r = _mock_redis()
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            with patch("redis.from_url", return_value=mock_r):
                mgr = get_cache_manager()
        assert isinstance(mgr, RedisCacheManager)

    def test_falls_back_to_memory_when_redis_unreachable(self):
        reset_cache_singleton()
        with patch.dict(os.environ, {"REDIS_URL": "redis://bad-host:6379/0"}):
            with patch("redis.from_url") as mock_from_url:
                mock_r = MagicMock()
                mock_r.ping.side_effect = Exception("connection refused")
                mock_from_url.return_value = mock_r
                mgr = get_cache_manager()
        assert isinstance(mgr, CacheManager)

    def test_singleton_returns_same_instance(self):
        a = get_cache_manager()
        b = get_cache_manager()
        assert a is b
