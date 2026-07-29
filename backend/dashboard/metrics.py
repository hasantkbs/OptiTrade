"""
OptiTrade Analytics & Dashboard Platform — shared statistical formulas.

Generalizes the per-trade Sharpe/Sortino/max-drawdown math already
proven in `paper_trading/analytics.py` into pure, series-agnostic
functions so `portfolio_dashboard.py`/`paper_trading_dashboard.py`/
`engine_dashboard.py` all share one implementation instead of each
recomputing it.
"""
from __future__ import annotations

import statistics
from typing import List, Optional


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
    if len(returns) < 2:
        return None
    stdev = statistics.stdev(returns)
    if stdev == 0:
        return None
    return statistics.mean(returns) / stdev


def compute_sortino_ratio(returns: List[float]) -> Optional[float]:
    if len(returns) < 2:
        return None
    downside = [r for r in returns if r < 0]
    if not downside:
        return None
    downside_deviation = statistics.pstdev(downside) if len(downside) > 1 else abs(downside[0])
    if downside_deviation == 0:
        return None
    return statistics.mean(returns) / downside_deviation


def compute_max_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd


def compute_win_rate(outcomes: List[bool]) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for outcome in outcomes if outcome) / len(outcomes)
