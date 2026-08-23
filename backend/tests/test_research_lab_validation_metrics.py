"""Deterministic unit tests for research_lab/validation/metrics.py."""
from datetime import datetime, timezone

import pytest

from research_lab.models import SimulatedTrade
from research_lab.validation import metrics


def _trade(net_return_pct, net_pnl=None, decided_at=None, horizon=5) -> SimulatedTrade:
    return SimulatedTrade(
        symbol="TESTSYM",
        decided_at=decided_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        evaluation_horizon_days=horizon,
        confidence=0.7,
        gross_return_pct=net_return_pct,
        commission_pct=0.0,
        slippage_spread_pct=0.0,
        tax_pct=0.0,
        net_return_pct=net_return_pct,
        net_pnl=net_pnl if net_pnl is not None else net_return_pct * 100.0,  # 1% of a $10,000 notional
    )


def test_win_rate_empty_list():
    assert metrics.win_rate([]) == 0.0


def test_win_rate_counts_positive_pnl_only():
    trades = [_trade(5.0), _trade(-2.0), _trade(3.0), _trade(-1.0)]
    assert metrics.win_rate(trades) == pytest.approx(0.5)


def test_profit_factor_none_when_no_losing_trades():
    assert metrics.profit_factor([_trade(5.0), _trade(3.0)]) is None


def test_profit_factor_none_for_empty_list():
    assert metrics.profit_factor([]) is None


def test_profit_factor_computes_gross_profit_over_gross_loss():
    trades = [_trade(10.0), _trade(-5.0)]  # net_pnl: +1000, -500
    assert metrics.profit_factor(trades) == pytest.approx(2.0)


def test_expectancy_pct_is_mean_net_return():
    trades = [_trade(10.0), _trade(-4.0), _trade(0.0)]
    assert metrics.expectancy_pct(trades) == pytest.approx(2.0)


def test_expectancy_pct_empty_list_is_zero():
    assert metrics.expectancy_pct([]) == 0.0


def test_equity_curve_compounds_in_chronological_order():
    later = _trade(10.0, decided_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    earlier = _trade(10.0, decided_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    curve = metrics.equity_curve([later, earlier], starting_equity=100.0)

    assert [point[0] for point in curve] == [earlier.decided_at, later.decided_at]
    assert curve[0][1] == pytest.approx(110.0)
    assert curve[1][1] == pytest.approx(121.0)


def test_equity_curve_empty_list_is_empty():
    assert metrics.equity_curve([]) == []


def test_monthly_returns_buckets_and_compounds_by_month():
    trades = [
        _trade(10.0, decided_at=datetime(2026, 1, 5, tzinfo=timezone.utc)),
        _trade(10.0, decided_at=datetime(2026, 1, 20, tzinfo=timezone.utc)),
        _trade(5.0, decided_at=datetime(2026, 2, 1, tzinfo=timezone.utc)),
    ]
    result = metrics.monthly_returns(trades)
    assert set(result.keys()) == {"2026-01", "2026-02"}
    assert result["2026-01"] == pytest.approx(21.0)  # 1.10 * 1.10 - 1 = 0.21
    assert result["2026-02"] == pytest.approx(5.0)


def test_yearly_returns_buckets_and_compounds_by_year():
    trades = [
        _trade(10.0, decided_at=datetime(2025, 12, 31, tzinfo=timezone.utc)),
        _trade(10.0, decided_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ]
    result = metrics.yearly_returns(trades)
    assert result["2025"] == pytest.approx(10.0)
    assert result["2026"] == pytest.approx(10.0)


def test_exposure_pct_sums_horizon_days_over_window():
    trades = [_trade(1.0, horizon=5), _trade(1.0, horizon=5)]
    assert metrics.exposure_pct(trades, window_days=20.0) == pytest.approx(50.0)


def test_exposure_pct_is_capped_at_100_percent():
    trades = [_trade(1.0, horizon=30), _trade(1.0, horizon=30)]
    assert metrics.exposure_pct(trades, window_days=10.0) == pytest.approx(100.0)


def test_exposure_pct_zero_window_days_is_zero():
    assert metrics.exposure_pct([_trade(1.0)], window_days=0.0) == 0.0
