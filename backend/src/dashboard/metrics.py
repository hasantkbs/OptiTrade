"""
OptiTrade Analytics & Dashboard Platform — shared statistical formulas.

Sharpe/Sortino/max-drawdown delegate to `core.performance_metrics` (the
single canonical implementation shared with `research_lab`, see that
module's docstring) rather than recomputing their own formulas - this
used to be a second, independently-drifting implementation. Only the
edge-case presentation contract (returning `None` when there isn't
enough data to compute a meaningful ratio, and this module's own
equity-curve/fraction conventions for drawdown) lives here; the actual
arithmetic is the canonical one.
"""
from __future__ import annotations

import statistics
from typing import List, Optional

from core import performance_metrics


def returns_from_equity_curve(equity_curve: List[float]) -> List[float]:
    """Simple period-over-period returns from a sequence of equity
    values. Zero/negative equity points are skipped (a return relative
    to a non-positive base is undefined)."""
    returns = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        if previous > 0:
            returns.append((current - previous) / previous)
    return returns


def compute_sharpe_ratio(returns: List[float]) -> Optional[float]:
    """`None` below mirrors this module's own long-standing "not enough
    data to mean anything" contract; whenever a real ratio IS computed,
    it's `core.performance_metrics.sharpe_ratio`'s value exactly (the
    two formulas are mathematically identical for the default
    risk_free_rate=0.0 case - dashboard's mean/stdev(returns) is the
    same division as canonical's mean(excess)/std(excess) once
    excess == returns)."""
    if len(returns) < 2:
        return None
    if statistics.stdev(returns) == 0:
        return None
    return performance_metrics.sharpe_ratio(returns)


def compute_sortino_ratio(returns: List[float]) -> Optional[float]:
    """`None` only for the "can't compute at all" case (fewer than two
    returns) - a period series with no downside at all is a real,
    meaningful result (`core.performance_metrics.sortino_ratio`'s
    capped value), not an absence of data."""
    if len(returns) < 2:
        return None
    return performance_metrics.sortino_ratio(returns)


def compute_max_drawdown(equity_curve: List[float]) -> float:
    """Same equity-curve-in/fraction-out contract this function has
    always had - internally converts to the canonical per-period-
    percent-return convention (`core.performance_metrics.max_drawdown`)
    and back, rather than re-deriving the peak-to-trough walk itself.
    Peak-to-trough drawdown *ratio* is scale-invariant, so this is
    numerically identical to computing it directly off the equity
    values."""
    returns_pct = [r * 100.0 for r in returns_from_equity_curve(equity_curve)]
    return performance_metrics.max_drawdown(returns_pct) / 100.0


def compute_win_rate(outcomes: List[bool]) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for outcome in outcomes if outcome) / len(outcomes)
