"""Unit tests for scripts/backfill_feature_store.py's pure logic (date
iteration, skip-if-exists check) - the actual end-to-end backfill run
against real Postgres/yfinance is exercised manually (Task 2's own
Step 5-7 below), not here, matching this plan's precedent for
scripts/evaluate_model_accuracy.py (no pytest coverage for a one-time,
real-network diagnostic script's main() - only its pure helper logic is
unit-tested)."""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone

from scripts.backfill_feature_store import (
    _price_period_to_days,
    already_backfilled,
    trading_days_in_range,
)


def test_trading_days_in_range_excludes_weekends():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)   # a Thursday
    end = datetime(2026, 1, 7, tzinfo=timezone.utc)     # the following Wednesday
    days = trading_days_in_range(start, end)
    weekdays = {d.weekday() for d in days}
    assert 5 not in weekdays and 6 not in weekdays  # no Saturday (5) or Sunday (6)
    assert len(days) == 5  # Thu, Fri, Mon, Tue, Wed


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


def test_price_period_to_days_parses_months_years_and_days():
    assert _price_period_to_days("6mo") == 180
    assert _price_period_to_days("1y") == 365
    assert _price_period_to_days("90d") == 90


def test_price_period_to_days_rejects_unrecognized_format():
    import pytest
    with pytest.raises(ValueError):
        _price_period_to_days("bogus")
