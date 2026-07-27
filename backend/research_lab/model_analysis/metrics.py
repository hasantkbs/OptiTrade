"""
OptiTrade Research Lab — trading-specific risk metrics.

Sharpe ratio, Sortino ratio, maximum drawdown, and expected value are
not computed anywhere else in this codebase (`core/risk_manager.py`
manages live position sizing/stop-loss levels, not historical
performance statistics) - these are new, real implementations, not
duplicates of anything existing.

All four operate on a plain chronological list of per-period percent
returns (e.g. each engine decision's `actual_return`, sourced from
`learning.persistence.LearningRepository.get_engine_outcomes`). Returns
are NOT assumed to be daily/equally spaced - trading decisions here
occur over variable horizons - so Sharpe/Sortino are deliberately left
non-annualized (a plain mean-over-dispersion ratio per period) rather
than scaled by an arbitrary sqrt(252) that would misrepresent
irregularly spaced samples.
"""
from __future__ import annotations

from typing import List

import numpy as np

_NO_DOWNSIDE_CAP = 10.0


def expected_value(returns: List[float]) -> float:
    if not returns:
        return 0.0
    return float(np.mean(returns))


def sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = np.array(returns) - risk_free_rate
    std = float(np.std(excess, ddof=1))
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std)


def sortino_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = np.array(returns) - risk_free_rate
    downside = np.minimum(excess, 0.0)
    downside_deviation = float(np.sqrt(np.mean(downside ** 2)))
    mean_excess = float(np.mean(excess))

    if downside_deviation == 0:
        return _NO_DOWNSIDE_CAP if mean_excess > 0 else 0.0
    return mean_excess / downside_deviation


def max_drawdown(returns: List[float]) -> float:
    """Largest peak-to-trough decline (as a positive percent) of the
    equity curve implied by compounding `returns` (each a percent, e.g.
    `2.5` for +2.5%) in chronological order."""
    if not returns:
        return 0.0

    equity = np.cumprod(1.0 + np.array(returns) / 100.0)
    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max
    return float(abs(np.min(drawdowns)) * 100.0)
