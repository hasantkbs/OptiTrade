"""
OptiTrade Research Lab — model analysis.

Combines Continuous Learning's already-computed accuracy/precision/
recall/calibration (`learning.accuracy.compute_accuracy_metrics`,
reused directly - never re-derived) with the new Sharpe/Sortino/
drawdown/expected-value metrics from `metrics.py`, both computed from
the exact same evaluated `EngineOutcomeRecord`s.
"""
from __future__ import annotations

from typing import List, Optional

from learning import accuracy as learning_accuracy
from learning.config import LearningConfig
from learning.models import EngineOutcomeRecord, RollingWindow
from research_lab.model_analysis import metrics
from research_lab.models import ModelAnalysisResult


def analyze(
    engine_name: str,
    engine_version: str,
    window: RollingWindow,
    outcomes: List[EngineOutcomeRecord],
    learning_config: Optional[LearningConfig] = None,
    risk_free_rate: float = 0.0,
) -> ModelAnalysisResult:
    accuracy_metrics = learning_accuracy.compute_accuracy_metrics(
        engine_name, engine_version, window, outcomes, learning_config,
    )
    evaluated_returns = [o.actual_return for o in outcomes if o.evaluated and o.actual_return is not None]

    return ModelAnalysisResult(
        engine_name=engine_name, engine_version=engine_version, window=window,
        accuracy_metrics=accuracy_metrics,
        sharpe_ratio=metrics.sharpe_ratio(evaluated_returns, risk_free_rate),
        sortino_ratio=metrics.sortino_ratio(evaluated_returns, risk_free_rate),
        max_drawdown=metrics.max_drawdown(evaluated_returns),
        expected_value=metrics.expected_value(evaluated_returns),
    )
