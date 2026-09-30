"""
Deterministic unit tests for research_lab/validation/benchmark.py. Price
data comes from an injected synthetic fetcher (matching
tests/test_ml_training_datasets.py's own pattern) - never a live network
call, so this is fast and reproducible."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from research_lab.validation import benchmark

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_END = datetime(2026, 1, 10, tzinfo=timezone.utc)


def _rising(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100.0 + i for i in range(len(dates))]}, index=dates)


def _empty(symbol, start, end):
    return pd.DataFrame({"Close": []})


def _none_fetcher(symbol, start, end):
    return None


def test_compute_benchmark_returns_total_return_and_sharpe():
    result = benchmark.compute_benchmark("SPY", _START, _END, price_fetcher=_rising)
    assert result is not None
    total_return_pct, sharpe = result
    assert total_return_pct > 0.0
    assert isinstance(sharpe, float)


def test_compute_benchmark_total_return_matches_first_and_last_close():
    result = benchmark.compute_benchmark("SPY", _START, _END, price_fetcher=_rising)
    total_return_pct, _sharpe = result
    dates = pd.date_range(start=_START, end=_END, freq="D", tz="UTC")
    first_close = 100.0
    last_close = 100.0 + (len(dates) - 1)
    expected = (last_close - first_close) / first_close * 100.0
    assert total_return_pct == pytest.approx(expected)


def test_compute_benchmark_returns_none_when_fetcher_returns_none():
    assert benchmark.compute_benchmark("SPY", _START, _END, price_fetcher=_none_fetcher) is None


def test_compute_benchmark_returns_none_when_history_is_empty():
    assert benchmark.compute_benchmark("SPY", _START, _END, price_fetcher=_empty) is None


def test_compute_benchmark_returns_none_when_history_has_a_single_row():
    def _single_row(symbol, start, end):
        return pd.DataFrame({"Close": [100.0]}, index=[start])

    assert benchmark.compute_benchmark("SPY", _START, _END, price_fetcher=_single_row) is None


def test_compute_benchmark_flat_price_series_has_zero_return_and_zero_sharpe():
    def _flat(symbol, start, end):
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        return pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)

    total_return_pct, sharpe = benchmark.compute_benchmark("SPY", _START, _END, price_fetcher=_flat)
    assert total_return_pct == pytest.approx(0.0)
    assert sharpe == pytest.approx(0.0)
