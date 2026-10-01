"""
Tests for engines/fundamental/feature_adapter.py.

Most tests use synthetic, deterministic `info` dicts and multi-year
financial-statement DataFrames (constructed directly) injected by
monkeypatching the fetch functions imported into
`engines.fundamental.feature_adapter` — deterministic, fast coverage of
the derivation math (growth rates, margin stability, earnings
consistency, Altman Z-Score) without depending on real, ever-changing
company financials. A final section runs one genuine, live-network +
real-database end-to-end test against a real company (AAPL).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from engines.fundamental.config import (
    ALL_FEATURE_NAMES,
    FEATURE_ALTMAN_Z,
    FEATURE_CASH_CONVERSION,
    FEATURE_EARNINGS_CONSISTENCY,
    FEATURE_MARGIN_STABILITY,
    FEATURE_OPERATING_INCOME_GROWTH,
    FEATURE_PE,
    FEATURE_ROIC,
    FundamentalEngineConfig,
)
from engines.fundamental.feature_adapter import FundamentalFeatureAdapter, _latest, _yoy_growth_pct
from feature_store.models import FeatureValue


def _financials_df() -> pd.DataFrame:
    columns = pd.to_datetime(["2025-09-30", "2024-09-30", "2023-09-30", "2022-09-30"])
    return pd.DataFrame(
        {
            columns[0]: {"Total Revenue": 1000.0, "Operating Income": 200.0, "Net Income": 150.0, "EBIT": 210.0, "Interest Expense": 10.0},
            columns[1]: {"Total Revenue": 900.0, "Operating Income": 150.0, "Net Income": 100.0, "EBIT": 160.0, "Interest Expense": 12.0},
            columns[2]: {"Total Revenue": 800.0, "Operating Income": 140.0, "Net Income": 90.0, "EBIT": 150.0, "Interest Expense": 14.0},
            columns[3]: {"Total Revenue": 700.0, "Operating Income": 100.0, "Net Income": -20.0, "EBIT": 110.0, "Interest Expense": 15.0},
        }
    )


def _balance_sheet_df() -> pd.DataFrame:
    columns = pd.to_datetime(["2025-09-30", "2024-09-30"])
    return pd.DataFrame(
        {
            columns[0]: {
                "Total Assets": 2000.0, "Total Liabilities Net Minority Interest": 800.0,
                "Working Capital": 300.0, "Retained Earnings": 500.0,
                "Invested Capital": 1200.0, "Total Debt": 400.0,
            },
            columns[1]: {
                "Total Assets": 1800.0, "Total Liabilities Net Minority Interest": 750.0,
                "Working Capital": 250.0, "Retained Earnings": 400.0,
                "Invested Capital": 1100.0, "Total Debt": 380.0,
            },
        }
    )


def _cashflow_df() -> pd.DataFrame:
    columns = pd.to_datetime(["2025-09-30", "2024-09-30"])
    return pd.DataFrame(
        {
            columns[0]: {"Operating Cash Flow": 250.0, "Free Cash Flow": 180.0},
            columns[1]: {"Operating Cash Flow": 200.0, "Free Cash Flow": 150.0},
        }
    )


def _info() -> dict:
    return {
        "trailingPE": 18.0, "forwardPE": 16.0, "pegRatio": 1.2,
        "priceToSalesTrailing12Months": 2.5, "priceToBook": 3.0, "enterpriseToEbitda": 12.0,
        "revenueGrowth": 0.15, "earningsGrowth": 0.10,
        "grossMargins": 0.45, "operatingMargins": 0.20, "profitMargins": 0.15,
        "returnOnEquity": 0.18, "returnOnAssets": 0.09,
        "debtToEquity": 60.0, "currentRatio": 1.5, "quickRatio": 1.1,
        "marketCap": 5000.0,
    }


@pytest.fixture
def adapter():
    return FundamentalFeatureAdapter(config=FundamentalEngineConfig())


@pytest.fixture
def symbol():
    return f"TEST-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def cleanup(adapter, symbol):
    yield
    conn = adapter.feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (symbol,))
    finally:
        adapter.feature_store.offline_store._pool.putconn(conn)
    for name in ALL_FEATURE_NAMES:
        adapter.feature_store.online_store._client.delete(f"feature_store:{symbol}:{name}")


def _patch_fetchers(monkeypatch, info=None, financials=None, balance_sheet=None, cashflow=None):
    monkeypatch.setattr("engines.fundamental.feature_adapter.fetch_info", lambda s: info if info is not None else {})
    monkeypatch.setattr(
        "engines.fundamental.feature_adapter.fetch_financials", lambda s: financials
    )
    monkeypatch.setattr(
        "engines.fundamental.feature_adapter.fetch_balance_sheet", lambda s: balance_sheet
    )
    monkeypatch.setattr(
        "engines.fundamental.feature_adapter.fetch_cashflow_statement", lambda s: cashflow
    )


# ─────────────────────────────────────────────────────────────────────────
# Small helper functions — edge cases
# ─────────────────────────────────────────────────────────────────────────

def test_latest_returns_none_when_series_is_all_nan():
    series = pd.Series([float("nan"), float("nan")])
    assert _latest(series) is None


def test_latest_returns_none_for_none_series():
    assert _latest(None) is None


def test_yoy_growth_returns_none_with_fewer_than_two_valid_years():
    series = pd.Series([100.0, float("nan"), float("nan")])
    assert _yoy_growth_pct(series) is None


def test_yoy_growth_returns_none_when_previous_value_is_zero():
    series = pd.Series([100.0, 0.0])
    assert _yoy_growth_pct(series) is None


def test_yoy_growth_returns_none_for_none_series():
    assert _yoy_growth_pct(None) is None


# ─────────────────────────────────────────────────────────────────────────
# _compute_all — synthetic, deterministic data
# ─────────────────────────────────────────────────────────────────────────

def test_compute_all_extracts_direct_info_fields(adapter, symbol, monkeypatch):
    _patch_fetchers(monkeypatch, info=_info())
    values = adapter._compute_all(symbol)
    assert values[FEATURE_PE] == 18.0


def test_compute_all_computes_operating_income_growth_from_financials(adapter, symbol, monkeypatch):
    _patch_fetchers(monkeypatch, info=_info(), financials=_financials_df())
    values = adapter._compute_all(symbol)
    # (200 - 150) / 150 * 100 = 33.33...
    assert values[FEATURE_OPERATING_INCOME_GROWTH] == pytest.approx(33.333, abs=0.01)


def test_compute_all_computes_roic_from_financials_and_balance_sheet(adapter, symbol, monkeypatch):
    _patch_fetchers(
        monkeypatch, info=_info(), financials=_financials_df(), balance_sheet=_balance_sheet_df()
    )
    values = adapter._compute_all(symbol)
    # EBIT[latest]=210, Invested Capital[latest]=1200 -> 210/1200*100 = 17.5
    assert values[FEATURE_ROIC] == pytest.approx(17.5)


def test_compute_all_computes_cash_conversion(adapter, symbol, monkeypatch):
    _patch_fetchers(
        monkeypatch, info=_info(), financials=_financials_df(), cashflow=_cashflow_df()
    )
    values = adapter._compute_all(symbol)
    # OCF[latest]=250, NetIncome[latest]=150 -> 250/150 = 1.6667
    assert values[FEATURE_CASH_CONVERSION] == pytest.approx(1.6667, abs=0.001)


def test_compute_all_computes_earnings_consistency(adapter, symbol, monkeypatch):
    _patch_fetchers(monkeypatch, info=_info(), financials=_financials_df())
    values = adapter._compute_all(symbol)
    # Net Income across 4 years: 150, 100, 90, -20 -> 3 of 4 positive = 0.75
    assert values[FEATURE_EARNINGS_CONSISTENCY] == pytest.approx(0.75)


def test_compute_all_computes_margin_stability(adapter, symbol, monkeypatch):
    _patch_fetchers(monkeypatch, info=_info(), financials=_financials_df())
    values = adapter._compute_all(symbol)
    assert FEATURE_MARGIN_STABILITY in values
    assert 0.0 <= values[FEATURE_MARGIN_STABILITY] <= 1.0


def test_compute_all_computes_altman_z_when_all_inputs_available(adapter, symbol, monkeypatch):
    _patch_fetchers(
        monkeypatch, info=_info(), financials=_financials_df(), balance_sheet=_balance_sheet_df()
    )
    values = adapter._compute_all(symbol)
    # 1.2*(300/2000) + 1.4*(500/2000) + 3.3*(210/2000) + 0.6*(5000/800) + 1.0*(1000/2000)
    # = 0.18 + 0.35 + 0.3465 + 3.75 + 0.5 = 5.1265
    assert values[FEATURE_ALTMAN_Z] == pytest.approx(5.1265, abs=0.001)


def test_compute_all_omits_altman_z_when_balance_sheet_missing(adapter, symbol, monkeypatch):
    _patch_fetchers(monkeypatch, info=_info(), financials=_financials_df(), balance_sheet=None)
    values = adapter._compute_all(symbol)
    assert FEATURE_ALTMAN_Z not in values


def test_compute_all_handles_completely_missing_data_gracefully(adapter, symbol, monkeypatch):
    _patch_fetchers(monkeypatch)  # everything None/empty
    values = adapter._compute_all(symbol)
    assert values == {}


def test_compute_all_writes_every_computed_feature_to_the_feature_store(adapter, symbol, monkeypatch):
    _patch_fetchers(monkeypatch, info=_info(), financials=_financials_df(), balance_sheet=_balance_sheet_df(), cashflow=_cashflow_df())
    values = adapter._compute_all(symbol)
    for name, value in values.items():
        record = adapter.feature_store.get_latest_feature(symbol, name)
        assert record is not None
        assert record.value == pytest.approx(value)


# ─────────────────────────────────────────────────────────────────────────
# get_features — cache hit / miss orchestration
# ─────────────────────────────────────────────────────────────────────────

def test_get_features_uses_cache_and_never_touches_the_network_when_all_fresh(adapter, symbol, monkeypatch):
    now = datetime.now(timezone.utc)
    for name in ALL_FEATURE_NAMES:
        adapter.feature_store.write_feature(
            FeatureValue(symbol=symbol, feature_name=name, value=1.23, event_timestamp=now)
        )

    def _raise_if_called(*args, **kwargs):
        raise AssertionError("should not be called when all features are fresh")

    monkeypatch.setattr("engines.fundamental.feature_adapter.fetch_info", _raise_if_called)
    monkeypatch.setattr("engines.fundamental.feature_adapter.fetch_financials", _raise_if_called)
    monkeypatch.setattr("engines.fundamental.feature_adapter.fetch_balance_sheet", _raise_if_called)
    monkeypatch.setattr("engines.fundamental.feature_adapter.fetch_cashflow_statement", _raise_if_called)

    resolution = adapter.get_features(symbol)
    assert set(resolution.from_cache) == set(ALL_FEATURE_NAMES)
    assert resolution.computed_fresh == []
    assert all(v == pytest.approx(1.23) for v in resolution.values.values())


def test_get_features_recomputes_when_stale(adapter, symbol, monkeypatch):
    stale = datetime.now(timezone.utc) - timedelta(days=2)
    adapter.feature_store.write_feature(
        FeatureValue(symbol=symbol, feature_name=FEATURE_PE, value=1.0, event_timestamp=stale)
    )
    _patch_fetchers(monkeypatch, info=_info())

    resolution = adapter.get_features(symbol)
    assert FEATURE_PE in resolution.computed_fresh
    assert resolution.values[FEATURE_PE] == 18.0


# ─────────────────────────────────────────────────────────────────────────
# Real, live end-to-end (network + Postgres + Redis)
# ─────────────────────────────────────────────────────────────────────────

def test_real_end_to_end_get_features_for_a_real_company():
    adapter = FundamentalFeatureAdapter(config=FundamentalEngineConfig())
    resolution = adapter.get_features("AAPL")
    assert FEATURE_PE in resolution.values
    assert resolution.values[FEATURE_PE] > 0

    conn = adapter.feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", ("AAPL",))
    finally:
        adapter.feature_store.offline_store._pool.putconn(conn)
    for name in ALL_FEATURE_NAMES:
        adapter.feature_store.online_store._client.delete(f"feature_store:AAPL:{name}")
