"""
OptiTrade Research Lab — feature drift analysis.

Two-sample Kolmogorov-Smirnov test (`scipy.stats.ks_2samp` - already an
existing project dependency via scikit-learn, reused rather than
hand-rolling a distribution-shift statistic) comparing a feature's
value distribution in a recent window against an earlier baseline
window. `drifted` is `True` when the test's p-value falls below the
configured significance level - the distributions are unlikely to be
the same.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from scipy.stats import ks_2samp

from feature_store.service import FeatureStoreService
from research_lab.config import ResearchLabConfig
from research_lab.models import FeatureDriftRecord


def compute_drift(
    feature_store: FeatureStoreService,
    symbol: str,
    feature_name: str,
    baseline_start: datetime,
    baseline_end: datetime,
    recent_start: datetime,
    recent_end: datetime,
    config: Optional[ResearchLabConfig] = None,
) -> Optional[FeatureDriftRecord]:
    config = config or ResearchLabConfig()
    baseline = feature_store.get_feature_history(symbol, feature_name, baseline_start, baseline_end)
    recent = feature_store.get_feature_history(symbol, feature_name, recent_start, recent_end)

    if len(baseline) < 2 or len(recent) < 2:
        return None

    baseline_values = [record.value for record in baseline]
    recent_values = [record.value for record in recent]

    result = ks_2samp(baseline_values, recent_values)
    drifted = bool(result.pvalue < config.significance_level)

    return FeatureDriftRecord(
        symbol=symbol, feature_name=feature_name, drift_statistic=float(result.statistic),
        p_value=float(result.pvalue), drifted=drifted,
        baseline_window_start=baseline_start, baseline_window_end=baseline_end,
        recent_window_start=recent_start, recent_window_end=recent_end,
        computed_at=datetime.now(timezone.utc),
    )
