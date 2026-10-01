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

import pandas as pd

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
    target_day = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class _FakeRecord:
        event_timestamp = target_day

    class _FakeStore:
        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return _FakeRecord()

    assert already_backfilled(_FakeStore(), "AAPL", target_day) is True


def test_already_backfilled_false_when_no_row(monkeypatch):
    class _FakeStore:
        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return None

    assert already_backfilled(_FakeStore(), "AAPL", datetime(2026, 1, 1, tzinfo=timezone.utc)) is False


def test_price_period_to_days_parses_months_years_and_days():
    assert _price_period_to_days("6mo") == 180
    assert _price_period_to_days("1y") == 365
    assert _price_period_to_days("90d") == 90


def test_price_period_to_days_rejects_unrecognized_format():
    import pytest
    with pytest.raises(ValueError):
        _price_period_to_days("bogus")
