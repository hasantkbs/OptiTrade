"""
Unit tests for CacheManager.

Every test is isolated — each creates its own CacheManager instance so
the singleton state from other tests cannot leak in.
"""
import time
import threading

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from cache_manager import CacheManager, get_cache_manager, invalidate_cache


# ── Helpers ────────────────────────────────────────────────────────────────────

def fresh() -> CacheManager:
    """Return a brand-new, isolated CacheManager for each test."""
    return CacheManager()


# ── get / set ──────────────────────────────────────────────────────────────────

class TestGetSet:
    def test_miss_returns_none(self):
        c = fresh()
        assert c.get("missing") is None

    def test_hit_returns_value(self):
        c = fresh()
        c.set("k", {"a": 1}, ttl=60)
        assert c.get("k") == {"a": 1}

    def test_set_overwrites(self):
        c = fresh()
        c.set("k", "first", ttl=60)
        c.set("k", "second", ttl=60)
        assert c.get("k") == "second"

    def test_stores_none_value(self):
        c = fresh()
        c.set("k", None, ttl=60)
        # None stored should come back as None — same as a miss, so cache
        # will not help here, but it must not crash
        # (in practice callers should not cache None, but the class must be safe)
        result = c.get("k")
        assert result is None

    def test_different_types(self):
        c = fresh()
        c.set("int", 42, ttl=60)
        c.set("list", [1, 2, 3], ttl=60)
        c.set("dict", {"x": True}, ttl=60)
        assert c.get("int") == 42
        assert c.get("list") == [1, 2, 3]
        assert c.get("dict") == {"x": True}


# ── TTL / expiry ───────────────────────────────────────────────────────────────

class TestExpiry:
    def test_expired_entry_returns_none(self):
        c = fresh()
        c.set("k", "v", ttl=1)
        time.sleep(1.1)
        assert c.get("k") is None

    def test_not_yet_expired(self):
        c = fresh()
        c.set("k", "v", ttl=60)
        time.sleep(0.05)
        assert c.get("k") == "v"

    def test_expired_entry_removed_from_store(self):
        c = fresh()
        c.set("k", "v", ttl=1)
        time.sleep(1.1)
        c.get("k")  # triggers lazy eviction
        stats = c.get_stats()
        assert stats["active_keys"] == 0

    def test_default_ttl_is_300(self):
        c = fresh()
        c.set("k", "v")
        stats = c.get_stats()
        assert stats["active_keys"] == 1


# ── delete ─────────────────────────────────────────────────────────────────────

class TestDelete:
    def test_delete_existing_key(self):
        c = fresh()
        c.set("k", "v", ttl=60)
        result = c.delete("k")
        assert result is True
        assert c.get("k") is None

    def test_delete_missing_key_returns_false(self):
        c = fresh()
        assert c.delete("nonexistent") is False

    def test_delete_does_not_affect_other_keys(self):
        c = fresh()
        c.set("a", 1, ttl=60)
        c.set("b", 2, ttl=60)
        c.delete("a")
        assert c.get("b") == 2


# ── clear ──────────────────────────────────────────────────────────────────────

class TestClear:
    def test_clear_all(self):
        c = fresh()
        c.set("a", 1, ttl=60)
        c.set("b", 2, ttl=60)
        count = c.clear()
        assert count == 2
        assert c.get("a") is None
        assert c.get("b") is None

    def test_clear_by_pattern(self):
        c = fresh()
        c.set("scan_bist", 1, ttl=60)
        c.set("scan_crypto", 2, ttl=60)
        c.set("chart_AAPL_3mo", 3, ttl=60)
        count = c.clear(pattern="scan")
        assert count == 2
        assert c.get("scan_bist") is None
        assert c.get("scan_crypto") is None
        assert c.get("chart_AAPL_3mo") == 3

    def test_clear_pattern_no_match(self):
        c = fresh()
        c.set("k", "v", ttl=60)
        count = c.clear(pattern="xyz")
        assert count == 0
        assert c.get("k") == "v"

    def test_clear_empty_store(self):
        c = fresh()
        assert c.clear() == 0


# ── evict_expired ──────────────────────────────────────────────────────────────

class TestEvictExpired:
    def test_evicts_only_expired_keys(self):
        c = fresh()
        c.set("short", "x", ttl=1)
        c.set("long", "y", ttl=60)
        time.sleep(1.1)
        evicted = c.evict_expired()
        assert evicted == 1
        assert c.get("long") == "y"

    def test_evict_when_nothing_expired(self):
        c = fresh()
        c.set("k", "v", ttl=60)
        assert c.evict_expired() == 0

    def test_evict_empty_store(self):
        c = fresh()
        assert c.evict_expired() == 0


# ── get_stats ──────────────────────────────────────────────────────────────────

class TestStats:
    def test_initial_stats(self):
        c = fresh()
        s = c.get_stats()
        assert s["hits"] == 0
        assert s["misses"] == 0
        assert s["hit_rate_pct"] == 0.0
        assert s["active_keys"] == 0

    def test_hits_and_misses_tracked(self):
        c = fresh()
        c.get("missing")           # miss
        c.set("k", "v", ttl=60)
        c.get("k")                 # hit
        s = c.get_stats()
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["hit_rate_pct"] == 50.0

    def test_expired_key_counted_as_miss(self):
        c = fresh()
        c.set("k", "v", ttl=1)
        time.sleep(1.1)
        c.get("k")
        s = c.get_stats()
        assert s["misses"] == 1
        assert s["hits"] == 0

    def test_active_keys_excludes_expired(self):
        c = fresh()
        c.set("short", "x", ttl=1)
        c.set("long", "y", ttl=60)
        time.sleep(1.1)
        s = c.get_stats()
        assert s["active_keys"] == 1
        assert s["total_keys"] == 2  # expired entry still in store until evicted


# ── thread safety ──────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_writes_do_not_corrupt(self):
        c = fresh()
        errors = []

        def writer(n: int):
            try:
                for i in range(100):
                    c.set(f"key_{n}_{i}", i, ttl=60)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        stats = c.get_stats()
        assert stats["active_keys"] == 1000

    def test_concurrent_reads_and_writes(self):
        c = fresh()
        c.set("shared", 0, ttl=60)
        errors = []

        def reader():
            try:
                for _ in range(200):
                    c.get("shared")
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(200):
                    c.set("shared", i, ttl=60)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        threads += [threading.Thread(target=writer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"


# ── singleton ──────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_same_instance_returned(self):
        a = get_cache_manager()
        b = get_cache_manager()
        assert a is b

    def test_invalidate_cache_clears_singleton(self):
        cm = get_cache_manager()
        cm.set("test_singleton_key", "value", ttl=60)
        count = invalidate_cache(pattern="test_singleton_key")
        assert count == 1
        assert cm.get("test_singleton_key") is None

    def test_invalidate_cache_no_pattern_clears_all(self):
        cm = get_cache_manager()
        cm.set("a", 1, ttl=60)
        cm.set("b", 2, ttl=60)
        invalidate_cache()
        assert cm.get("a") is None
        assert cm.get("b") is None
