"""
Tests for feature_store/offline_store.py, run against the real, local
PostgreSQL instance (see docker-compose.yml / FEATURE_STORE_POSTGRES_*
env vars) — not mocked, so schema creation, point-in-time query
semantics, and append-only behavior are genuinely exercised. Every test
uses a unique, randomly-suffixed test symbol and deletes its own rows in
teardown, so this never disturbs any other data in the shared `optitrade`
database/table.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from feature_store.config import FeatureStoreConfig
from feature_store.models import FeatureRecord
from feature_store.offline_store import PostgresOfflineStore


@pytest.fixture(scope="module")
def store():
    s = PostgresOfflineStore(config=FeatureStoreConfig.from_env())
    yield s
    s.close()


@pytest.fixture
def symbol():
    """A unique symbol per test so rows never collide with other tests or
    any pre-existing data, and can be cleanly deleted afterward."""
    return f"TEST-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def cleanup(store, symbol):
    yield
    conn = store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (symbol,))
    finally:
        store._pool.putconn(conn)


def _record(symbol: str, feature_name="rsi_14", value=55.5, event_timestamp=None) -> FeatureRecord:
    now = datetime.now(timezone.utc)
    return FeatureRecord(
        symbol=symbol, feature_name=feature_name, value=value,
        event_timestamp=event_timestamp or now, ingestion_timestamp=now,
    )


def test_ping_succeeds_against_real_postgres(store):
    assert store.ping() is True


def test_schema_is_created_idempotently(store):
    # _init_schema() already ran once in the store fixture; running it
    # again must not raise (CREATE TABLE/INDEX IF NOT EXISTS).
    store._init_schema()


def test_get_latest_returns_none_when_nothing_written(store, symbol):
    assert store.get_latest(symbol, "rsi_14") is None


def test_insert_then_get_latest_round_trips(store, symbol):
    record = _record(symbol, value=55.5)
    store.insert(record)

    fetched = store.get_latest(symbol, "rsi_14")
    assert fetched is not None
    assert fetched.symbol == symbol
    assert fetched.value == 55.5
    assert fetched.event_timestamp == record.event_timestamp


def test_get_latest_returns_the_most_recent_event_timestamp(store, symbol):
    now = datetime.now(timezone.utc)
    store.insert(_record(symbol, value=1.0, event_timestamp=now - timedelta(days=2)))
    store.insert(_record(symbol, value=2.0, event_timestamp=now - timedelta(days=1)))
    store.insert(_record(symbol, value=3.0, event_timestamp=now))

    assert store.get_latest(symbol, "rsi_14").value == 3.0


def test_get_as_of_returns_the_value_known_at_that_time_point_in_time_correctness(store, symbol):
    now = datetime.now(timezone.utc)
    store.insert(_record(symbol, value=1.0, event_timestamp=now - timedelta(days=2)))
    store.insert(_record(symbol, value=2.0, event_timestamp=now - timedelta(days=1)))
    store.insert(_record(symbol, value=3.0, event_timestamp=now))

    # As of a time before ANY write existed -> nothing known yet.
    assert store.get_as_of(symbol, "rsi_14", now - timedelta(days=3)) is None
    # As of a time between the first and second write -> only the first is known.
    assert store.get_as_of(symbol, "rsi_14", now - timedelta(days=1, hours=12)).value == 1.0
    # As of a time between the second and third write -> the second is known.
    assert store.get_as_of(symbol, "rsi_14", now - timedelta(hours=12)).value == 2.0
    # As of now -> all three are known, most recent wins.
    assert store.get_as_of(symbol, "rsi_14", now).value == 3.0


def test_later_writes_never_change_an_earlier_point_in_time_answer(store, symbol):
    # This is the core append-only/point-in-time guarantee: querying "as
    # of T" before and after a later write for a *different* moment in
    # time must return the identical answer both times.
    now = datetime.now(timezone.utc)
    store.insert(_record(symbol, value=1.0, event_timestamp=now - timedelta(days=1)))

    as_of_before_second_write = store.get_as_of(symbol, "rsi_14", now - timedelta(hours=12))
    assert as_of_before_second_write.value == 1.0

    # A later write, further in the future, must not retroactively alter
    # the answer for a query timestamp that precedes it.
    store.insert(_record(symbol, value=99.0, event_timestamp=now))
    as_of_same_point_again = store.get_as_of(symbol, "rsi_14", now - timedelta(hours=12))
    assert as_of_same_point_again.value == 1.0


def test_different_feature_names_on_the_same_symbol_are_independent(store, symbol):
    store.insert(_record(symbol, feature_name="rsi_14", value=1.0))
    store.insert(_record(symbol, feature_name="macd", value=2.0))
    assert store.get_latest(symbol, "rsi_14").value == 1.0
    assert store.get_latest(symbol, "macd").value == 2.0


def test_insert_wraps_a_real_database_error_in_featurestoreerror(store, symbol):
    from feature_store.exceptions import FeatureStoreError

    # A genuine psycopg2 error, not simulated: close the pool's
    # connections out from under it, then try to use it.
    store._pool.closeall()
    try:
        with pytest.raises(FeatureStoreError):
            store.insert(_record(symbol))
    finally:
        # Restore a usable pool so the module-scoped `store` fixture and
        # any later test in this file keep working.
        store._pool = store._pool.__class__(
            1, 5,
            host=store._config.postgres_host, port=store._config.postgres_port,
            dbname=store._config.postgres_db, user=store._config.postgres_user,
            password=store._config.postgres_password,
        )


def test_get_as_of_wraps_a_real_database_error_in_featurestoreerror(store, symbol):
    from feature_store.exceptions import FeatureStoreError

    store._pool.closeall()
    try:
        with pytest.raises(FeatureStoreError):
            store.get_as_of(symbol, "rsi_14", datetime.now(timezone.utc))
    finally:
        store._pool = store._pool.__class__(
            1, 5,
            host=store._config.postgres_host, port=store._config.postgres_port,
            dbname=store._config.postgres_db, user=store._config.postgres_user,
            password=store._config.postgres_password,
        )


def test_version_is_persisted_and_returned(store, symbol):
    now = datetime.now(timezone.utc)
    record = FeatureRecord(
        symbol=symbol, feature_name="rsi_14", value=1.0, version="v2",
        event_timestamp=now, ingestion_timestamp=now,
    )
    store.insert(record)
    fetched = store.get_latest(symbol, "rsi_14")
    assert fetched.version == "v2"


# ─────────────────────────────────────────────────────────────────────────
# get_history - added for Research Lab feature analysis (correlation/
# stability/drift), which needs every recorded value in a range, not just
# the latest or a single as-of point.
# ─────────────────────────────────────────────────────────────────────────

def test_get_history_returns_empty_list_when_nothing_written(store, symbol):
    now = datetime.now(timezone.utc)
    assert store.get_history(symbol, "rsi_14", now - timedelta(days=5), now) == []


def test_get_history_returns_every_value_in_range_oldest_first(store, symbol):
    now = datetime.now(timezone.utc)
    for i in range(5):
        store.insert(_record(symbol, value=float(i), event_timestamp=now - timedelta(days=4 - i)))

    history = store.get_history(symbol, "rsi_14", now - timedelta(days=10), now)
    assert [r.value for r in history] == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_get_history_excludes_values_outside_the_range(store, symbol):
    now = datetime.now(timezone.utc)
    store.insert(_record(symbol, value=1.0, event_timestamp=now - timedelta(days=20)))
    store.insert(_record(symbol, value=2.0, event_timestamp=now - timedelta(days=1)))

    history = store.get_history(symbol, "rsi_14", now - timedelta(days=5), now)
    assert [r.value for r in history] == [2.0]


def test_get_history_only_returns_the_requested_feature_name(store, symbol):
    now = datetime.now(timezone.utc)
    store.insert(_record(symbol, feature_name="rsi_14", value=1.0, event_timestamp=now))
    store.insert(_record(symbol, feature_name="macd_line", value=2.0, event_timestamp=now))

    history = store.get_history(symbol, "rsi_14", now - timedelta(days=1), now + timedelta(days=1))
    assert len(history) == 1
    assert history[0].feature_name == "rsi_14"


def test_get_history_wraps_a_real_database_error_in_featurestoreerror(store, symbol):
    from feature_store.exceptions import FeatureStoreError

    store._pool.closeall()
    try:
        with pytest.raises(FeatureStoreError):
            store.get_history(symbol, "rsi_14", datetime.now(timezone.utc) - timedelta(days=1), datetime.now(timezone.utc))
    finally:
        store._pool = store._pool.__class__(
            1, 5,
            host=store._config.postgres_host, port=store._config.postgres_port,
            dbname=store._config.postgres_db, user=store._config.postgres_user,
            password=store._config.postgres_password,
        )


# ─────────────────────────────────────────────────────────────────────────
# list_feature_names - added for the ML Training Platform's feature
# extractor, which needs to auto-discover every feature currently
# recorded for a symbol rather than depending on a hardcoded list.
# ─────────────────────────────────────────────────────────────────────────

def test_list_feature_names_returns_empty_list_when_nothing_written(store, symbol):
    assert store.list_feature_names(symbol) == []


def test_list_feature_names_returns_every_distinct_feature_name(store, symbol):
    store.insert(_record(symbol, feature_name="rsi_14", value=50.0))
    store.insert(_record(symbol, feature_name="macd_line", value=1.0))
    store.insert(_record(symbol, feature_name="pe_ratio", value=20.0))

    names = store.list_feature_names(symbol)
    assert set(names) == {"rsi_14", "macd_line", "pe_ratio"}


def test_list_feature_names_does_not_duplicate_repeated_writes(store, symbol):
    store.insert(_record(symbol, feature_name="rsi_14", value=50.0))
    store.insert(_record(symbol, feature_name="rsi_14", value=55.0))
    names = store.list_feature_names(symbol)
    assert names.count("rsi_14") == 1


def test_list_feature_names_scoped_to_the_requested_symbol_only(store, symbol):
    other_symbol = f"{symbol}-OTHER"
    store.insert(_record(symbol, feature_name="rsi_14", value=50.0))
    store.insert(_record(other_symbol, feature_name="macd_line", value=1.0))
    try:
        names = store.list_feature_names(symbol)
        assert names == ["rsi_14"]
    finally:
        conn = store._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (other_symbol,))
        finally:
            store._pool.putconn(conn)


def test_list_feature_names_wraps_a_real_database_error_in_featurestoreerror(store, symbol):
    from feature_store.exceptions import FeatureStoreError

    store._pool.closeall()
    try:
        with pytest.raises(FeatureStoreError):
            store.list_feature_names(symbol)
    finally:
        store._pool = store._pool.__class__(
            1, 5,
            host=store._config.postgres_host, port=store._config.postgres_port,
            dbname=store._config.postgres_db, user=store._config.postgres_user,
            password=store._config.postgres_password,
        )
