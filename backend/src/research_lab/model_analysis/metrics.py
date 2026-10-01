"""
OptiTrade Research Lab — trading-specific risk metrics.

Re-exports the canonical Sharpe/Sortino/max-drawdown/expected-value
implementations from `core.performance_metrics` (production code) -
research_lab is free to depend on production (never the other way
around, see `tests/test_research_isolation.py`), so this module is now
a thin compatibility shim: every existing `research_lab`/`ml_training`
caller (`from research_lab.model_analysis import metrics` /
`from research_lab.model_analysis.metrics import _NO_DOWNSIDE_CAP`)
keeps working unchanged, while `dashboard/metrics.py` (production)
reuses the exact same math through `core.performance_metrics` directly
instead of a second, independently-drifting implementation.
"""
from __future__ import annotations

from core.performance_metrics import (
    NO_DOWNSIDE_CAP as _NO_DOWNSIDE_CAP,
    expected_value,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
)

__all__ = ["expected_value", "sharpe_ratio", "sortino_ratio", "max_drawdown", "_NO_DOWNSIDE_CAP"]
