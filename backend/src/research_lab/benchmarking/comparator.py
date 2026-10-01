"""
OptiTrade Research Lab — benchmarking comparator.

Compares two named subjects of the same type (engine versions, feature
sets, weighting policies, or models) using a two-sample t-test
(`scipy.stats.ttest_ind`, already an existing project dependency) over
their historical return series, plus each subject's own
`model_analysis` metrics for context.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from scipy.stats import ttest_ind

from research_lab.config import ResearchLabConfig
from research_lab.model_analysis import metrics
from research_lab.models import BenchmarkResult, BenchmarkSubjectType, RollingWindow


def _metrics_dict(returns: List[float], risk_free_rate: float) -> Dict[str, float]:
    return {
        "sample_count": float(len(returns)),
        "expected_value": metrics.expected_value(returns),
        "sharpe_ratio": metrics.sharpe_ratio(returns, risk_free_rate),
        "sortino_ratio": metrics.sortino_ratio(returns, risk_free_rate),
        "max_drawdown": metrics.max_drawdown(returns),
        "win_rate": (sum(1 for value in returns if value > 0) / len(returns)) if returns else 0.0,
    }


def compare(
    subject_type: BenchmarkSubjectType,
    subject_a: str,
    subject_b: str,
    returns_a: List[float],
    returns_b: List[float],
    window: RollingWindow,
    config: Optional[ResearchLabConfig] = None,
    experiment_id: Optional[int] = None,
) -> BenchmarkResult:
    config = config or ResearchLabConfig()
    metrics_a = _metrics_dict(returns_a, config.risk_free_rate)
    metrics_b = _metrics_dict(returns_b, config.risk_free_rate)

    if len(returns_a) >= 2 and len(returns_b) >= 2:
        test_result = ttest_ind(returns_a, returns_b, equal_var=False)
        p_value = float(test_result.pvalue)
    else:
        p_value = 1.0

    significant = p_value < config.significance_level

    return BenchmarkResult(
        experiment_id=experiment_id, subject_type=subject_type, subject_a=subject_a, subject_b=subject_b,
        window=window, metrics_a=metrics_a, metrics_b=metrics_b, p_value=p_value, significant=significant,
        created_at=datetime.now(timezone.utc),
    )
