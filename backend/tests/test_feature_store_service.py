"""
Tests for feature_store/service.py.

Orchestration logic (cache-miss fallback, validation rejection,
best-effort cache-refresh failure handling) is tested in isolation using
fakes that satisfy `feature_store.interfaces`' Protocols — the same
approach used for `core.hybrid_engine.HybridTradingEngine` in Sprint 1
Task 6. A final section runs the same behavior end-to-end against the
real Redis + PostgreSQL instances, with a unique test symbol cleaned up
in teardown, to prove the real components integrate correctly through
the real service, not just through fakes.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest

from feature_store.config import FeatureStoreConfig
from feature_store.exceptions import FeatureValidationError
from feature_store.models import FeatureRecord, FeatureValue, ValidationResult
from feature_store.offline_store import PostgresOfflineStore
from feature_store.online_store import RedisOnlineStore
from feature_store.service import FeatureStoreService
from feature_store.validation import FeatureValidator


class FakeOnlineStore:
    def __init__(self) -> None:
        self._data: Dict[str, FeatureRecord] = {}
        self.get_calls: List[tuple] = []
        self.set_calls: List[FeatureRecord] = []
        self.raise_on_set = False

    def get_latest(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]:
        self.get_calls.append((symbol, feature_name))
        return self._data.get((symbol, feature_name))

    def set_latest(self, record: FeatureRecord) -> None:
        self.set_calls.append(record)
        if self.raise_on_set:
            raise ConnectionError("simulated redis outage")
        self._data[(record.symbol, record.feature_name)] = record

    def ping(self) -> bool:
        return True


class FakeOfflineStore:
    def __init__(self) -> None:
        self._data: Dict[str, FeatureRecord] = {}
        self.insert_calls: List[FeatureRecord] = []

    def insert(self, record: FeatureRecord) -> None:
        self.insert_calls.append(record)
        self._data[(record.symbol, record.feature_name)] = record

    def get_latest(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]:
        return self._data.get((symbol, feature_name))

    def get_as_of(self, symbol: str, feature_name: str, as_of: datetime) -> Optional[FeatureRecord]:
        record = self._data.get((symbol, feature_name))
        if record is not None and record.event_timestamp <= as_of:
            return record
        return None

    def get_history(self, symbol: str, feature_name: str, start: datetime, end: datetime) -> List[FeatureRecord]:
        record = self._data.get((symbol, feature_name))
        if record is not None and start <= record.event_timestamp <= end:
            return [record]
        return []

    def list_feature_names(self, symbol: str) -> List[str]:
        return [name for (sym, name) in self._data if sym == symbol]

    def ping(self) -> bool:
        return True


class RejectAllValidator:
    def validate(self, feature: FeatureValue) -> ValidationResult:
        return ValidationResult(is_valid=False, errors=["always rejected"])


def _fv(symbol="BTC-USD", feature_name="rsi_14", value=55.5) -> FeatureValue:
    return FeatureValue(symbol=symbol, feature_name=feature_name, value=value)


# ─────────────────────────────────────────────────────────────────────────
# Orchestration logic, via fakes
# ─────────────────────────────────────────────────────────────────────────

def test_write_feature_persists_to_both_stores():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    service = FeatureStoreService(online_store=online, offline_store=offline)

    record = service.write_feature(_fv(value=55.5))

    assert record.value == 55.5
    assert len(offline.insert_calls) == 1
    assert len(online.set_calls) == 1


def test_write_feature_raises_and_does_not_persist_when_validation_fails():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    service = FeatureStoreService(online_store=online, offline_store=offline, validator=RejectAllValidator())

    with pytest.raises(FeatureValidationError):
        service.write_feature(_fv())

    assert offline.insert_calls == []
    assert online.set_calls == []


def test_write_feature_succeeds_even_if_the_online_cache_refresh_fails():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    online.raise_on_set = True
    service = FeatureStoreService(online_store=online, offline_store=offline)

    # Must not raise - the offline store (source of truth) already has it.
    record = service.write_feature(_fv(value=55.5))
    assert record.value == 55.5
    assert len(offline.insert_calls) == 1


def test_get_latest_feature_reads_from_online_store_first():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    service = FeatureStoreService(online_store=online, offline_store=offline)
    service.write_feature(_fv(value=1.0))

    service.get_latest_feature("BTC-USD", "rsi_14")
    # Two get_calls: read-through logic always checks online first.
    assert online.get_calls[-1] == ("BTC-USD", "rsi_14")


def test_get_latest_feature_falls_back_to_offline_on_cache_miss_and_repopulates_cache():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    service = FeatureStoreService(online_store=online, offline_store=offline)

    # Write directly to the offline store only, bypassing the service's
    # write path, to simulate a genuine cache miss (data exists offline,
    # nothing cached online yet).
    now = datetime.now(timezone.utc)
    record = FeatureRecord(
        symbol="BTC-USD", feature_name="rsi_14", value=42.0,
        event_timestamp=now, ingestion_timestamp=now,
    )
    offline.insert(record)

    assert online.get_latest("BTC-USD", "rsi_14") is None  # confirm true miss
    fetched = service.get_latest_feature("BTC-USD", "rsi_14")
    assert fetched is not None and fetched.value == 42.0
    # Repopulated into the online cache as a side effect of the miss.
    assert online.get_latest("BTC-USD", "rsi_14") is not None


def test_get_latest_feature_returns_none_when_nowhere_found():
    service = FeatureStoreService(online_store=FakeOnlineStore(), offline_store=FakeOfflineStore())
    assert service.get_latest_feature("BTC-USD", "rsi_14") is None


def test_get_latest_features_batch_omits_missing_names_rather_than_raising():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    service = FeatureStoreService(online_store=online, offline_store=offline)
    service.write_feature(_fv(feature_name="rsi_14", value=1.0))

    result = service.get_latest_features("BTC-USD", ["rsi_14", "does_not_exist"])
    assert result == {"rsi_14": 1.0}


def test_write_features_batch_writes_every_value_with_a_shared_timestamp():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    service = FeatureStoreService(online_store=online, offline_store=offline)

    records = service.write_features("BTC-USD", {"rsi_14": 55.5, "macd": 0.2})
    assert {r.feature_name for r in records} == {"rsi_14", "macd"}
    assert records[0].event_timestamp == records[1].event_timestamp


def test_get_feature_as_of_only_ever_queries_the_offline_store():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    service = FeatureStoreService(online_store=online, offline_store=offline)
    service.write_feature(_fv(value=1.0))

    as_of = service.get_feature_as_of("BTC-USD", "rsi_14", datetime.now(timezone.utc))
    assert as_of is not None and as_of.value == 1.0
    # The online store's get_latest must never have been consulted for this call.
    assert ("BTC-USD", "rsi_14") not in [c for c in online.get_calls]  # only from write's set, not a get


def test_get_feature_history_only_ever_queries_the_offline_store():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    service = FeatureStoreService(online_store=online, offline_store=offline)
    service.write_feature(_fv(value=1.0))

    now = datetime.now(timezone.utc)
    history = service.get_feature_history("BTC-USD", "rsi_14", now - timedelta(days=1), now + timedelta(days=1))
    assert len(history) == 1
    assert history[0].value == 1.0
    assert ("BTC-USD", "rsi_14") not in [c for c in online.get_calls]


def test_list_feature_names_delegates_to_the_offline_store():
    service = FeatureStoreService(online_store=FakeOnlineStore(), offline_store=FakeOfflineStore())
    service.write_feature(_fv(symbol="BTC-USD", feature_name="rsi_14", value=1.0))
    service.write_feature(_fv(symbol="BTC-USD", feature_name="macd_line", value=2.0))
    assert set(service.list_feature_names("BTC-USD")) == {"rsi_14", "macd_line"}


def test_health_check_reports_both_stores():
    service = FeatureStoreService(online_store=FakeOnlineStore(), offline_store=FakeOfflineStore())
    assert service.health_check() == {"online_store_available": True, "offline_store_available": True}


class UnavailableStore:
    def get_latest(self, symbol, feature_name):
        return None

    def set_latest(self, record):
        pass

    def insert(self, record):
        pass

    def get_as_of(self, symbol, feature_name, as_of):
        return None

    def ping(self) -> bool:
        raise ConnectionError("down")


def test_health_check_reports_false_when_online_store_is_unreachable():
    service = FeatureStoreService(online_store=UnavailableStore(), offline_store=FakeOfflineStore())
    result = service.health_check()
    assert result["online_store_available"] is False
    assert result["offline_store_available"] is True


def test_health_check_reports_false_when_offline_store_is_unreachable():
    service = FeatureStoreService(online_store=FakeOnlineStore(), offline_store=UnavailableStore())
    result = service.health_check()
    assert result["online_store_available"] is True
    assert result["offline_store_available"] is False


def test_get_latest_feature_still_returns_the_record_even_if_cache_repopulation_fails():
    online, offline = FakeOnlineStore(), FakeOfflineStore()
    online.raise_on_set = True
    service = FeatureStoreService(online_store=online, offline_store=offline)

    now = datetime.now(timezone.utc)
    offline.insert(FeatureRecord(
        symbol="BTC-USD", feature_name="rsi_14", value=42.0,
        event_timestamp=now, ingestion_timestamp=now,
    ))

    # Cache miss -> falls back to offline -> tries (and fails) to repopulate
    # the cache -> must still return the value it found offline.
    fetched = service.get_latest_feature("BTC-USD", "rsi_14")
    assert fetched is not None
    assert fetched.value == 42.0


# ─────────────────────────────────────────────────────────────────────────
# End-to-end, against the real Redis + PostgreSQL instances
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def real_service():
    config = FeatureStoreConfig.from_env()
    online = RedisOnlineStore(config=config)
    offline = PostgresOfflineStore(config=config)
    yield FeatureStoreService(online_store=online, offline_store=offline, validator=FeatureValidator())
    offline.close()


@pytest.fixture
def real_symbol():
    return f"TEST-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def cleanup_real(real_service, real_symbol):
    yield
    conn = real_service.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (real_symbol,))
    finally:
        real_service.offline_store._pool.putconn(conn)
    real_service.online_store._client.delete(f"feature_store:{real_symbol}:rsi_14")


def test_real_end_to_end_write_and_read(real_service, real_symbol):
    real_service.write_feature(FeatureValue(symbol=real_symbol, feature_name="rsi_14", value=61.2))

    latest = real_service.get_latest_feature(real_symbol, "rsi_14")
    assert latest is not None
    assert latest.value == 61.2

    as_of_future = real_service.get_feature_as_of(
        real_symbol, "rsi_14", datetime.now(timezone.utc) + timedelta(seconds=5)
    )
    assert as_of_future is not None
    assert as_of_future.value == 61.2

    as_of_past = real_service.get_feature_as_of(
        real_symbol, "rsi_14", datetime.now(timezone.utc) - timedelta(days=1)
    )
    assert as_of_past is None


def test_real_health_check(real_service):
    assert real_service.health_check() == {
        "online_store_available": True,
        "offline_store_available": True,
    }


def test_real_validation_rejects_nan_before_it_reaches_either_store(real_service, real_symbol):
    import math

    with pytest.raises(FeatureValidationError):
        real_service.write_feature(FeatureValue(symbol=real_symbol, feature_name="rsi_14", value=math.nan))

    assert real_service.get_latest_feature(real_symbol, "rsi_14") is None
