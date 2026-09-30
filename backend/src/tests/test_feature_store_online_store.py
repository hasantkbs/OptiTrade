"""
Tests for feature_store/online_store.py, run against a real, local Redis
instance (see docker-compose.yml / FEATURE_STORE_REDIS_* env vars) — not
mocked, so the actual serialization/TTL/connectivity behavior is
genuinely exercised. Uses Redis logical DB 15 (a separate keyspace from
DB 0, which config.py defaults to) so test data never touches whatever
DB 0 is used for, and flushes only DB 15 between tests.
"""
from datetime import datetime, timezone

import pytest

from feature_store.config import FeatureStoreConfig
from feature_store.models import FeatureRecord
from feature_store.online_store import RedisOnlineStore


@pytest.fixture
def store():
    config = FeatureStoreConfig(
        postgres_host="unused", postgres_port=0, postgres_db="unused",
        postgres_user="unused", postgres_password="unused",
        redis_host="localhost", redis_port=6379, redis_db=15,
        online_ttl_seconds=60,
    )
    s = RedisOnlineStore(config=config)
    s._client.flushdb()
    yield s
    s._client.flushdb()


def _record(symbol="BTC-USD", feature_name="rsi_14", value=55.5) -> FeatureRecord:
    now = datetime.now(timezone.utc)
    return FeatureRecord(
        symbol=symbol, feature_name=feature_name, value=value,
        event_timestamp=now, ingestion_timestamp=now,
    )


def test_ping_succeeds_against_real_redis(store):
    assert store.ping() is True


def test_get_latest_returns_none_for_missing_key(store):
    assert store.get_latest("BTC-USD", "rsi_14") is None


def test_set_then_get_latest_round_trips_correctly(store):
    record = _record(value=55.5)
    store.set_latest(record)

    fetched = store.get_latest("BTC-USD", "rsi_14")
    assert fetched is not None
    assert fetched.symbol == "BTC-USD"
    assert fetched.feature_name == "rsi_14"
    assert fetched.value == 55.5
    assert fetched.event_timestamp == record.event_timestamp
    assert fetched.ingestion_timestamp == record.ingestion_timestamp


def test_different_symbols_and_feature_names_are_independent(store):
    store.set_latest(_record(symbol="BTC-USD", feature_name="rsi_14", value=1.0))
    store.set_latest(_record(symbol="ETH-USD", feature_name="rsi_14", value=2.0))
    store.set_latest(_record(symbol="BTC-USD", feature_name="macd", value=3.0))

    assert store.get_latest("BTC-USD", "rsi_14").value == 1.0
    assert store.get_latest("ETH-USD", "rsi_14").value == 2.0
    assert store.get_latest("BTC-USD", "macd").value == 3.0


def test_set_latest_overwrites_the_previous_value(store):
    store.set_latest(_record(value=1.0))
    store.set_latest(_record(value=2.0))
    assert store.get_latest("BTC-USD", "rsi_14").value == 2.0


def test_get_latest_degrades_to_none_on_a_real_connection_failure():
    # A genuine, unreachable Redis (nothing listens on this port), not
    # simulated - proves get_latest treats a real connectivity failure as
    # a miss instead of raising, per the store's documented contract.
    config = FeatureStoreConfig(
        postgres_host="unused", postgres_port=0, postgres_db="unused",
        postgres_user="unused", postgres_password="unused",
        redis_host="localhost", redis_port=1, redis_db=15,
        online_ttl_seconds=60,
    )
    unreachable = RedisOnlineStore(config=config)
    assert unreachable.get_latest("BTC-USD", "rsi_14") is None


def test_set_latest_degrades_to_a_no_op_on_a_real_connection_failure():
    config = FeatureStoreConfig(
        postgres_host="unused", postgres_port=0, postgres_db="unused",
        postgres_user="unused", postgres_password="unused",
        redis_host="localhost", redis_port=1, redis_db=15,
        online_ttl_seconds=60,
    )
    unreachable = RedisOnlineStore(config=config)
    unreachable.set_latest(_record())  # must not raise


def test_ping_returns_false_on_a_real_connection_failure():
    config = FeatureStoreConfig(
        postgres_host="unused", postgres_port=0, postgres_db="unused",
        postgres_user="unused", postgres_password="unused",
        redis_host="localhost", redis_port=1, redis_db=15,
        online_ttl_seconds=60,
    )
    unreachable = RedisOnlineStore(config=config)
    assert unreachable.ping() is False


def test_value_expires_after_the_configured_ttl():
    # Redis' SET ... EX rejects 0 outright (ResponseError: invalid expire
    # time), it does not treat it as "expire immediately" - verified
    # directly against the real server. The smallest meaningful positive
    # TTL is 1 whole second (EX is second-granularity), so this test uses
    # a real, short sleep rather than a 0 TTL.
    import time

    config = FeatureStoreConfig(
        postgres_host="unused", postgres_port=0, postgres_db="unused",
        postgres_user="unused", postgres_password="unused",
        redis_host="localhost", redis_port=6379, redis_db=15,
        online_ttl_seconds=1,
    )
    s = RedisOnlineStore(config=config)
    s._client.flushdb()
    try:
        s.set_latest(_record())
        assert s.get_latest("BTC-USD", "rsi_14") is not None
        time.sleep(1.5)
        assert s.get_latest("BTC-USD", "rsi_14") is None
    finally:
        s._client.flushdb()
