"""Unit tests for scripts/backfill_feature_store.py's pure logic (date
iteration, skip-if-exists check) - the actual end-to-end backfill run
against real Postgres/yfinance is exercised manually (Task 2's own
Step 5-7 below), not here, matching this plan's precedent for
scripts/evaluate_model_accuracy.py (no pytest coverage for a one-time,
real-network diagnostic script's main() - only its pure helper logic is
unit-tested)."""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone

import httpx

import scripts.backfill_feature_store as backfill_feature_store
from providers.binance_provider import BinanceProvider
from scripts.backfill_feature_store import (
    _price_period_to_days,
    already_backfilled,
    trading_days_in_range,
)


def test_trading_days_in_range_excludes_weekends_by_default():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)  # Monday
    end = datetime(2024, 1, 7, tzinfo=timezone.utc)    # Sunday
    days = trading_days_in_range(start, end)
    assert all(d.weekday() < 5 for d in days)
    assert len(days) == 5


def test_trading_days_in_range_includes_weekends_for_crypto():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)  # Monday
    end = datetime(2024, 1, 7, tzinfo=timezone.utc)    # Sunday
    days = trading_days_in_range(start, end, include_weekends=True)
    assert len(days) == 7
    assert any(d.weekday() >= 5 for d in days)


def test_already_backfilled_true_when_row_exists(monkeypatch):
    """Every feature queried for this day resolves to a record (a
    generic stand-in for "all 17 ALL_FEATURE_NAMES are present") ->
    already_backfilled is True."""
    target_day = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class _FakeRecord:
        event_timestamp = target_day

    class _FakeStore:
        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return _FakeRecord()

    assert already_backfilled(_FakeStore(), "AAPL", target_day) is True


def test_already_backfilled_true_when_all_features_present():
    """Explicitly checks every one of ALL_FEATURE_NAMES is queried and
    all resolve to a record for the day -> True."""
    from engines.technical.config import ALL_FEATURE_NAMES

    target_day = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class _FakeRecord:
        event_timestamp = target_day

    queried = []

    class _FakeStore:
        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            queried.append(feature_name)
            return _FakeRecord()

    assert already_backfilled(_FakeStore(), "AAPL", target_day) is True
    # every known feature name must have actually been checked
    assert set(ALL_FEATURE_NAMES).issubset(set(queried))


def test_already_backfilled_false_when_no_row(monkeypatch):
    class _FakeStore:
        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return None

    assert already_backfilled(_FakeStore(), "AAPL", datetime(2026, 1, 1, tzinfo=timezone.utc)) is False


def test_already_backfilled_false_when_only_some_features_present():
    """Simulates a crash mid-write-loop: only one of the 17
    ALL_FEATURE_NAMES has a row for this day (e.g. the process died
    right after writing the first feature). already_backfilled must
    report False so the day gets fully redone on resume, rather than
    being wrongly treated as complete with its other ~16 features
    permanently missing."""
    from engines.technical.config import FEATURE_TREND_STRENGTH

    target_day = datetime(2026, 1, 1, tzinfo=timezone.utc)
    written_features = {FEATURE_TREND_STRENGTH}  # only the first feature "landed"

    class _FakeRecord:
        event_timestamp = target_day

    class _FakeStore:
        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return _FakeRecord() if feature_name in written_features else None

    assert already_backfilled(_FakeStore(), "AAPL", target_day) is False


def test_already_backfilled_requires_as_of_at_or_after_event_timestamp():
    """Regression test for the Critical idempotency bug: a store with
    REALISTIC point-in-time semantics (event_timestamp <= as_of, mirroring
    PostgresOfflineStore.get_as_of's real SQL) recognizes a row written at
    a day's 23:59:59 when queried with that same day-end instant, but NOT
    when queried with that day's midnight - even though it's the exact
    same row, for the exact same day. The OTHER already_backfilled tests
    above use a FakeStore that always returns a record regardless of
    `as_of`, so none of them could see this: `backfill_symbol` was calling
    `already_backfilled(store, symbol, day)` (day = midnight-or-start's-
    time-of-day) while writing at `day`'s 23:59:59, so the check could
    never see its own writes and always returned False - silently
    double-writing on every re-run."""
    day = datetime(2026, 1, 1, tzinfo=timezone.utc)
    day_end_utc = datetime(2026, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    class _FakeRecord:
        def __init__(self, event_timestamp):
            self.event_timestamp = event_timestamp

    class _FakeRealisticStore:
        """Only returns the row when `as_of` is at or after when it was
        actually written - the real `get_as_of`'s `event_timestamp <=
        as_of` contract, unlike the other tests' unconditional fakes."""

        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            record = _FakeRecord(day_end_utc)
            return record if record.event_timestamp <= as_of else None

    store = _FakeRealisticStore()
    # Queried with the SAME instant the row was actually written at (what
    # the fixed backfill_symbol now does) -> correctly recognized.
    assert already_backfilled(store, "AAPL", day_end_utc) is True
    # Queried with that day's midnight (what the pre-fix backfill_symbol
    # was doing) -> the 23:59:59 row isn't "visible" yet as of midnight,
    # so it's wrongly NOT recognized as backfilled. This is the exact bug.
    assert already_backfilled(store, "AAPL", day) is False


def test_already_backfilled_normalizes_non_utc_session_timezone():
    """Regression test: the DB session's timezone must not affect this
    check. A record whose event_timestamp, when read back, reports a
    DIFFERENT tzinfo than UTC (simulating a non-UTC session) but the
    SAME real instant must still match correctly."""
    from datetime import timezone as tz

    class _FakeRecord:
        def __init__(self, event_timestamp):
            self.event_timestamp = event_timestamp

    class _FakeStore:
        def __init__(self, record):
            self._record = record

        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return self._record

    # A record whose event_timestamp is the SAME real instant as
    # 2024-06-15T23:59:59Z, but represented in a +02:00 offset (as a
    # non-UTC session timezone might return it) - the real instant is
    # the same calendar day in UTC terms, so this must still count as
    # a match.
    day = datetime(2024, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    same_instant_other_tz = day.astimezone(tz(timedelta(hours=2)))
    record = _FakeRecord(event_timestamp=same_instant_other_tz)
    store = _FakeStore(record)

    from engines.technical.config import ALL_FEATURE_NAMES
    store.get_as_of = lambda symbol, feature_name, as_of, respect_ingestion_time=False: record

    assert backfill_feature_store.already_backfilled(store, "TESTSYM", day) is True


def test_backfill_symbol_is_idempotent_across_runs(monkeypatch):
    """End-to-end regression test for Critical 1: running backfill_symbol
    twice over the SAME (symbol, day) range must write once and skip the
    second time - not silently double every row, which is what the
    pre-fix day/day_end_utc mismatch between the skip-check and the write
    caused (PostgresOfflineStore.insert() has no unique constraint / no
    ON CONFLICT to fall back on)."""
    import pandas as pd

    from engines.technical.config import ALL_FEATURE_NAMES, TechnicalEngineConfig
    import scripts.backfill_feature_store as mod

    day = datetime(2026, 1, 5, tzinfo=timezone.utc)  # a Monday

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end):
            idx = pd.date_range("2025-06-01", periods=400, freq="D", tz="UTC")
            return pd.DataFrame(
                {"Open": range(len(idx)), "Close": range(len(idx)), "Volume": [1000] * len(idx)}, index=idx,
            )

    class _FakeRealisticStore:
        """Mirrors PostgresOfflineStore's real point-in-time semantics
        (event_timestamp <= as_of, most recent wins) - see the test
        above for why this matters and the other fakes in this file
        don't."""

        def __init__(self):
            self.records = []

        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            candidates = [
                r for r in self.records
                if r.symbol == symbol and r.feature_name == feature_name and r.event_timestamp <= as_of
            ]
            return max(candidates, key=lambda r: r.event_timestamp) if candidates else None

        def insert(self, record):
            self.records.append(record)

    monkeypatch.setattr(mod.yf, "Ticker", _FakeTicker)
    monkeypatch.setattr(mod, "compute_technical_features", lambda window, config: {name: 1.0 for name in ALL_FEATURE_NAMES})

    store = _FakeRealisticStore()
    config = TechnicalEngineConfig()

    written_first = mod.backfill_symbol(store, config, "AAPL", day, day)
    assert written_first == 1
    assert len(store.records) == len(ALL_FEATURE_NAMES)

    written_second = mod.backfill_symbol(store, config, "AAPL", day, day)
    assert written_second == 0  # must be skipped, NOT double-written
    assert len(store.records) == len(ALL_FEATURE_NAMES)  # unchanged - no duplicate rows


def test_backfill_symbol_skips_non_finite_feature_values(monkeypatch):
    """Regression test for Important 4: a non-finite (NaN/Inf) feature
    value must be skipped and logged, never inserted - direct-insert
    writes bypass FeatureValidator.validate()'s NaN/Inf rejection, so
    backfill_symbol must apply its own guard."""
    import math

    import pandas as pd

    from engines.technical.config import ALL_FEATURE_NAMES, TechnicalEngineConfig
    import scripts.backfill_feature_store as mod

    day = datetime(2026, 1, 5, tzinfo=timezone.utc)  # a Monday
    bad_feature = ALL_FEATURE_NAMES[0]

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end):
            idx = pd.date_range("2025-06-01", periods=400, freq="D", tz="UTC")
            return pd.DataFrame(
                {"Open": range(len(idx)), "Close": range(len(idx)), "Volume": [1000] * len(idx)}, index=idx,
            )

    class _FakeStore:
        def __init__(self):
            self.records = []

        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return None  # never already backfilled

        def insert(self, record):
            self.records.append(record)

    def _fake_compute(window, config):
        values = {name: 1.0 for name in ALL_FEATURE_NAMES}
        values[bad_feature] = float("nan")
        return values

    monkeypatch.setattr(mod.yf, "Ticker", _FakeTicker)
    monkeypatch.setattr(mod, "compute_technical_features", _fake_compute)

    store = _FakeStore()
    config = TechnicalEngineConfig()

    mod.backfill_symbol(store, config, "AAPL", day, day)

    written_names = {r.feature_name for r in store.records}
    assert bad_feature not in written_names  # the NaN value must never be inserted
    assert all(math.isfinite(r.value) for r in store.records)
    assert len(written_names) == len(ALL_FEATURE_NAMES) - 1  # every OTHER feature still written


def test_price_period_to_days_parses_months_years_and_days():
    assert _price_period_to_days("6mo") == 180
    assert _price_period_to_days("1y") == 365
    assert _price_period_to_days("90d") == 90


def test_price_period_to_days_rejects_unrecognized_format():
    import pytest
    with pytest.raises(ValueError):
        _price_period_to_days("bogus")


def test_fetch_ohlcv_range_requests_the_full_date_bounded_window(monkeypatch):
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            # Two daily candles, matching Binance's real klines array shape.
            return [
                [1700000000000, "100", "105", "95", "102", "10", 0, "0", 0, "0", "0", "0"],
                [1700086400000, "102", "108", "100", "106", "12", 0, "0", 0, "0", "0", "0"],
            ]

    def _fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse()

    monkeypatch.setattr(httpx, "get", _fake_get)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 3, tzinfo=timezone.utc)
    result = BinanceProvider().fetch_ohlcv_range("BTC-USD", start, end)

    assert result is not None
    assert len(result) == 2
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert captured["params"]["symbol"] == "BTCUSDT"
    assert captured["params"]["interval"] == "1d"
    assert captured["params"]["startTime"] == int(start.timestamp() * 1000)
    assert captured["params"]["endTime"] == int(end.timestamp() * 1000)
    assert captured["params"]["limit"] == 1000


def test_fetch_ohlcv_range_returns_none_on_empty_response(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse())
    result = BinanceProvider().fetch_ohlcv_range("ETH-USD", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 2, tzinfo=timezone.utc))
    assert result is None


def test_backfill_symbol_routes_crypto_through_binance_not_yfinance(monkeypatch):
    import pandas as pd

    binance_called = {"was": False}
    yfinance_called = {"was": False}

    def _fake_fetch_ohlcv_range(self, symbol, start, end):
        binance_called["was"] = True
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        return pd.DataFrame({"Open": 100.0, "High": 105.0, "Low": 95.0, "Close": 102.0, "Volume": 10.0}, index=dates)

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start=None, end=None):
            yfinance_called["was"] = True
            return pd.DataFrame()

    monkeypatch.setattr(BinanceProvider, "fetch_ohlcv_range", _fake_fetch_ohlcv_range)
    monkeypatch.setattr(backfill_feature_store.yf, "Ticker", _FakeTicker)

    hist = backfill_feature_store._fetch_backfill_history(
        "BTC-USD", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 10, tzinfo=timezone.utc),
    )

    assert binance_called["was"] is True
    assert yfinance_called["was"] is False
    assert not hist.empty


def test_backfill_symbol_routes_equities_through_yfinance_not_binance(monkeypatch):
    import pandas as pd

    binance_called = {"was": False}

    def _fake_fetch_ohlcv_range(self, symbol, start, end):
        binance_called["was"] = True
        return None

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start=None, end=None):
            return pd.DataFrame({"Open": [100.0]}, index=pd.date_range("2024-01-01", periods=1, tz="UTC"))

    monkeypatch.setattr(BinanceProvider, "fetch_ohlcv_range", _fake_fetch_ohlcv_range)
    monkeypatch.setattr(backfill_feature_store.yf, "Ticker", _FakeTicker)

    hist = backfill_feature_store._fetch_backfill_history(
        "THYAO.IS", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 10, tzinfo=timezone.utc),
    )

    assert binance_called["was"] is False
    assert not hist.empty
