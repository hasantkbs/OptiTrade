"""
OptiTrade Research Lab — Decision Engine validation: trade-level metrics.

Sharpe/Sortino/max-drawdown are NOT re-derived here - `core.
performance_metrics` (the one canonical implementation every production
and research consumer already shares) is called directly on the trade
series' `net_return_pct` values. This module only adds the metrics that
implementation doesn't cover: win rate, profit factor, expectancy, the
equity curve, and monthly/yearly/exposure breakdowns - all operating on
`SimulatedTrade`s, never on raw price data.

Every trade is treated as a sequential, non-overlapping realized event
ordered by `decided_at` (a signal-level report, not a full concurrent-
position portfolio simulation - the task asks for these statistics as
metrics to compute, not for a new position-tracking engine). This is a
documented simplification, not a fabrication: `exposure_pct` is
explicitly an upper-bound approximation for the same reason.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from research_lab.models import SimulatedTrade


def win_rate(trades: List[SimulatedTrade]) -> float:
    if not trades:
        return 0.0
    return sum(1 for t in trades if t.net_pnl > 0) / len(trades)


def profit_factor(trades: List[SimulatedTrade]) -> Optional[float]:
    """gross profit / gross loss. `None` (not `inf`) when there are no
    losing trades to divide by - undefined, not infinite, and `None`
    round-trips through JSON where `float("inf")` would not."""
    gross_profit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gross_loss = sum(-t.net_pnl for t in trades if t.net_pnl < 0)
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def expectancy_pct(trades: List[SimulatedTrade]) -> float:
    """Mean net return per trade, in percent - "how much do I expect to
    make, on average, per trade taken"."""
    if not trades:
        return 0.0
    return sum(t.net_return_pct for t in trades) / len(trades)


def equity_curve(trades: List[SimulatedTrade], starting_equity: float = 100.0) -> List[Tuple[datetime, float]]:
    sorted_trades = sorted(trades, key=lambda t: t.decided_at)
    equity = starting_equity
    curve: List[Tuple[datetime, float]] = []
    for trade in sorted_trades:
        equity *= 1.0 + trade.net_return_pct / 100.0
        curve.append((trade.decided_at, equity))
    return curve


def _bucketed_compounded_returns(trades: List[SimulatedTrade], key_format: str) -> Dict[str, float]:
    buckets: Dict[str, List[float]] = defaultdict(list)
    for trade in trades:
        buckets[trade.decided_at.strftime(key_format)].append(trade.net_return_pct)

    result: Dict[str, float] = {}
    for key, returns in buckets.items():
        compounded = 1.0
        for r in returns:
            compounded *= 1.0 + r / 100.0
        result[key] = (compounded - 1.0) * 100.0
    return result


def monthly_returns(trades: List[SimulatedTrade]) -> Dict[str, float]:
    """`{"YYYY-MM": compounded_net_return_pct}` for every month with at
    least one trade."""
    return _bucketed_compounded_returns(trades, "%Y-%m")


def yearly_returns(trades: List[SimulatedTrade]) -> Dict[str, float]:
    """`{"YYYY": compounded_net_return_pct}` for every year with at
    least one trade."""
    return _bucketed_compounded_returns(trades, "%Y")


def exposure_pct(trades: List[SimulatedTrade], window_days: float) -> float:
    """Sum of every trade's `evaluation_horizon_days` divided by the
    report window's total length, capped at 100% - concurrent
    overlapping trades are not modeled (see module docstring), so this
    is an upper bound on time genuinely spent with an open position,
    not an exact figure."""
    if window_days <= 0:
        return 0.0
    total_days_in_market = sum(t.evaluation_horizon_days for t in trades)
    return min(100.0, (total_days_in_market / window_days) * 100.0)
