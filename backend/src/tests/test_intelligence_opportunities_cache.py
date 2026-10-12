"""Tests for intelligence/opportunities_cache.py. Real Redis (an
isolated logical DB, matching dashboard/scheduler.py's own test
convention)."""
import pytest
import redis

from intelligence.opportunities_cache import OpportunitiesCache


@pytest.fixture
def redis_client():
    client = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def cache(redis_client):
    return OpportunitiesCache(redis_client=redis_client, ttl_seconds=300)


def test_get_returns_none_before_any_set(cache):
    assert cache.get("TR") is None


def test_set_then_get_round_trips_the_payload(cache):
    cache.set("TR", '{"market": "TR", "opportunities": []}')
    assert cache.get("TR") == '{"market": "TR", "opportunities": []}'


def test_markets_are_independent_cache_keys(cache):
    cache.set("TR", "tr-payload")
    cache.set("US", "us-payload")
    assert cache.get("TR") == "tr-payload"
    assert cache.get("US") == "us-payload"


def test_set_applies_the_configured_ttl(cache, redis_client):
    cache.set("CRYPTO", "payload")
    ttl = redis_client.ttl("market:opportunities:CRYPTO")
    assert 0 < ttl <= 300


def test_redis_errors_are_caught_not_raised():
    class _BrokenRedis:
        def get(self, key):
            raise redis.RedisError("boom")

        def set(self, *args, **kwargs):
            raise redis.RedisError("boom")

    cache = OpportunitiesCache(redis_client=_BrokenRedis())
    cache.set("TR", "payload")  # must not raise
    assert cache.get("TR") is None
