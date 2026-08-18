"""Tests for dashboard/metrics.py. Pure math - no infra."""
import pytest

from core import performance_metrics
from dashboard.metrics import (
    compute_max_drawdown,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    compute_win_rate,
    returns_from_equity_curve,
)


def test_returns_from_equity_curve():
    returns = returns_from_equity_curve([100.0, 110.0, 99.0])
    assert returns[0] == pytest.approx(0.1)
    assert returns[1] == pytest.approx(-0.1)


def test_returns_from_equity_curve_skips_non_positive_base():
    returns = returns_from_equity_curve([0.0, 100.0, 110.0])
    assert len(returns) == 1
    assert returns[0] == pytest.approx(0.1)


def test_compute_sharpe_ratio_requires_at_least_two_returns():
    assert compute_sharpe_ratio([]) is None
    assert compute_sharpe_ratio([0.1]) is None


def test_compute_sharpe_ratio_none_for_zero_stdev():
    assert compute_sharpe_ratio([0.1, 0.1, 0.1]) is None


def test_compute_sharpe_ratio_positive_for_positive_mean_returns():
    sharpe = compute_sharpe_ratio([0.05, 0.02, -0.01, 0.03])
    assert sharpe is not None
    assert sharpe > 0


def test_compute_sortino_ratio_requires_at_least_two_returns():
    assert compute_sortino_ratio([]) is None
    assert compute_sortino_ratio([0.1]) is None


def test_compute_sortino_ratio_capped_without_downside():
    # No negative return at all, with a positive mean - a real,
    # meaningful (capped) result now that this delegates to the
    # canonical core.performance_metrics formula, not an absence of
    # data, so it's no longer None (production audit MEDIUM #1).
    assert compute_sortino_ratio([0.05, 0.02, 0.03]) == performance_metrics.NO_DOWNSIDE_CAP


def test_compute_sortino_ratio_with_downside():
    sortino = compute_sortino_ratio([0.05, -0.02, 0.03, -0.01])
    assert sortino is not None


def test_compute_max_drawdown_empty():
    assert compute_max_drawdown([]) == 0.0


def test_compute_max_drawdown_no_drawdown():
    assert compute_max_drawdown([100.0, 110.0, 120.0]) == 0.0


def test_compute_max_drawdown_typical():
    assert compute_max_drawdown([100.0, 200.0, 100.0]) == pytest.approx(0.5)


def test_compute_win_rate_empty():
    assert compute_win_rate([]) == 0.0


def test_compute_win_rate_typical():
    assert compute_win_rate([True, True, False, False]) == 0.5


# ─────────────────────────────────────────────────────────────────────────
# Canonical-equivalence regression (production audit MEDIUM #1: dashboard
# and research_lab used to independently implement Sharpe/Sortino/
# max-drawdown, risking silent formula drift between the two). Both now
# delegate to core.performance_metrics - these tests prove the dashboard
# wrapper's real-data path really does compute the canonical value, not
# just "some plausible-looking number".
# ─────────────────────────────────────────────────────────────────────────

def test_compute_sharpe_ratio_matches_the_canonical_implementation():
    returns = [0.05, 0.02, -0.01, 0.03, -0.02, 0.01]
    assert compute_sharpe_ratio(returns) == pytest.approx(performance_metrics.sharpe_ratio(returns))


def test_compute_sortino_ratio_matches_the_canonical_implementation():
    returns = [0.05, -0.02, 0.03, -0.01, 0.04]
    assert compute_sortino_ratio(returns) == pytest.approx(performance_metrics.sortino_ratio(returns))


def test_compute_max_drawdown_matches_the_canonical_implementation_scaled():
    equity_curve = [1000.0, 1200.0, 900.0, 950.0, 1300.0, 800.0]
    returns_pct = [r * 100.0 for r in returns_from_equity_curve(equity_curve)]
    expected = performance_metrics.max_drawdown(returns_pct) / 100.0
    assert compute_max_drawdown(equity_curve) == pytest.approx(expected)
