"""Unit tests for scripts/backfill_sec_fundamentals.py's pure logic -
period selection, point-in-time write idempotency, and derived-ratio
math. A fake in-memory store stands in for PostgresOfflineStore (same
get_history/insert contract), so these never touch a real database.
The actual end-to-end run against SEC's live API is exercised
manually, matching test_train_ml_candidate.py's own precedent."""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone

import pandas as pd
import pytest

from feature_store.models import FeatureRecord
from scripts.backfill_sec_fundamentals import (
    _annual_observations,
    _price_on_or_after,
    _write_derived_ratios,
    _write_observations,
)


class _FakeOfflineStore:
    """Minimal stand-in for PostgresOfflineStore - same get_history/
    insert contract, in-memory, no database."""

    def __init__(self) -> None:
        self.records: list[FeatureRecord] = []

    def get_history(self, symbol, feature_name, start, end):
        return [
            r for r in self.records
            if r.symbol == symbol and r.feature_name == feature_name and start <= r.event_timestamp <= end
        ]

    def insert(self, record: FeatureRecord) -> None:
        self.records.append(record)


# ── _annual_observations ──────────────────────────────────────────────

def test_annual_observations_keeps_only_10k_form():
    observations = [
        {"form": "10-Q", "end": "2024-12-31", "filed": "2024-06-01", "val": 999},
        {"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 100},
    ]
    result = _annual_observations(observations)
    assert set(result.keys()) == {"2024-12-31"}
    assert result["2024-12-31"]["val"] == 100


def test_annual_observations_picks_the_latest_filed_10k_per_period():
    observations = [
        {"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 100},
        {"form": "10-K", "end": "2024-12-31", "filed": "2025-05-01", "val": 110},  # a later-filed 10-K for the same period
    ]
    result = _annual_observations(observations)
    assert result["2024-12-31"]["val"] == 110
    assert result["2024-12-31"]["filed"] == "2025-05-01"


def test_annual_observations_excludes_10ka_amendments():
    """Deliberate first-pass simplification (see module docstring) -
    10-K/A amendments are still backfilled as raw observations
    (_write_observations doesn't filter by form), just excluded from
    ratio computation here."""
    observations = [
        {"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 100},
        {"form": "10-K/A", "end": "2024-12-31", "filed": "2025-08-01", "val": 90},
    ]
    result = _annual_observations(observations)
    assert result["2024-12-31"]["val"] == 100


# ── _write_observations ──────────────────────────────────────────────

def test_write_observations_writes_new_filings():
    store = _FakeOfflineStore()
    observations = [
        {"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 100.0},
    ]
    written = _write_observations(store, "AAPL", "sec_total_assets", observations)
    assert written == 1
    assert store.records[0].symbol == "AAPL"
    assert store.records[0].feature_name == "sec_total_assets"
    assert store.records[0].value == 100.0
    assert store.records[0].event_timestamp.date() == datetime(2025, 2, 15).date()
    # Honest backdate - ingestion_timestamp must match event_timestamp, not "now"
    assert store.records[0].ingestion_timestamp == store.records[0].event_timestamp


def test_write_observations_skips_already_backfilled_filed_dates():
    store = _FakeOfflineStore()
    observations = [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 100.0}]
    _write_observations(store, "AAPL", "sec_total_assets", observations)
    written_again = _write_observations(store, "AAPL", "sec_total_assets", observations)
    assert written_again == 0
    assert len(store.records) == 1


def test_write_observations_skips_non_finite_and_missing_values():
    store = _FakeOfflineStore()
    observations = [
        {"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": float("nan")},
        {"form": "10-K", "end": "2023-12-31", "filed": "2024-02-15", "val": None},
        {"form": "10-K", "end": "2022-12-31", "filed": None, "val": 50.0},
    ]
    written = _write_observations(store, "AAPL", "sec_total_assets", observations)
    assert written == 0
    assert store.records == []


# ── _price_on_or_after ──────────────────────────────────────────────

def test_price_on_or_after_finds_first_matching_price():
    idx = pd.date_range("2025-01-01", periods=5, freq="D", tz="UTC")
    history = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=idx)
    price = _price_on_or_after(history, datetime(2025, 1, 3, tzinfo=timezone.utc))
    assert price == 12.0


def test_price_on_or_after_returns_none_past_the_end_of_history():
    idx = pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC")
    history = pd.DataFrame({"Close": [10.0, 11.0, 12.0]}, index=idx)
    assert _price_on_or_after(history, datetime(2025, 6, 1, tzinfo=timezone.utc)) is None


# ── _write_derived_ratios ──────────────────────────────────────────────

def test_write_derived_ratios_computes_expected_ratios():
    store = _FakeOfflineStore()
    raw = {
        "sec_total_assets": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 1000.0}],
        "sec_total_liabilities": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 400.0}],
        "sec_stockholders_equity": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 600.0}],
        "sec_revenue": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 500.0}],
        "sec_net_income": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 60.0}],
        "sec_operating_income": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 80.0}],
        "sec_eps_diluted": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 2.0}],
        "sec_shares_outstanding": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 30.0}],
    }
    idx = pd.date_range("2025-02-14", periods=5, freq="D", tz="UTC")
    price_history = pd.DataFrame({"Close": [20.0, 20.0, 20.0, 20.0, 20.0]}, index=idx)

    written = _write_derived_ratios(store, "AAPL", raw, price_history)
    by_name = {r.feature_name: r.value for r in store.records}

    assert written == len(by_name)
    assert by_name["sec_debt_to_equity_pct"] == pytest.approx(400 / 600 * 100)
    assert by_name["sec_roe_pct"] == pytest.approx(60 / 600 * 100)
    assert by_name["sec_roa_pct"] == pytest.approx(60 / 1000 * 100)
    assert by_name["sec_net_margin_pct"] == pytest.approx(60 / 500 * 100)
    assert by_name["sec_operating_margin_pct"] == pytest.approx(80 / 500 * 100)
    assert by_name["sec_pe_ratio"] == pytest.approx(20.0 / 2.0)
    assert by_name["sec_pb_ratio"] == pytest.approx(20.0 / (600.0 / 30.0))
    assert "sec_revenue_growth_yoy_pct" not in by_name  # only one period - no prior year to compare


def test_write_derived_ratios_computes_yoy_growth_with_two_periods():
    store = _FakeOfflineStore()
    raw = {
        "sec_revenue": [
            {"form": "10-K", "end": "2023-12-31", "filed": "2024-02-15", "val": 400.0},
            {"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 500.0},
        ],
    }
    written = _write_derived_ratios(store, "AAPL", raw, None)
    by_name = {r.feature_name: r.value for r in store.records}
    assert written == 1
    assert by_name["sec_revenue_growth_yoy_pct"] == pytest.approx((500 - 400) / 400 * 100)


def test_write_derived_ratios_skips_cleanly_when_no_price_history():
    store = _FakeOfflineStore()
    raw = {
        "sec_revenue": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 500.0}],
        "sec_net_income": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 60.0}],
        "sec_eps_diluted": [{"form": "10-K", "end": "2024-12-31", "filed": "2025-02-15", "val": 2.0}],
    }
    written = _write_derived_ratios(store, "AAPL", raw, None)  # price_history=None
    by_name = {r.feature_name: r.value for r in store.records}
    assert "sec_pe_ratio" not in by_name
    assert by_name["sec_net_margin_pct"] == pytest.approx(60 / 500 * 100)
    assert written == len(by_name)
