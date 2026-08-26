"""
OptiTrade Research Lab — report content generation.

Pure functions assembling already-computed data (model analysis
results, backtest/benchmark results, experiments, hypotheses) into a
structured `content` dict. Never queries anything itself - `service.py`
owns all data access.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from learning.models import RollingWindow
from research_lab.models import (
    BacktestResult,
    BenchmarkResult,
    Experiment,
    Hypothesis,
    ModelAnalysisResult,
)


def _model_analysis_summary(result: ModelAnalysisResult) -> dict:
    return {
        "engine_name": result.engine_name,
        "engine_version": result.engine_version,
        "window": result.window.value,
        "sample_count": result.accuracy_metrics.sample_count,
        "accuracy": result.accuracy_metrics.accuracy,
        "precision": result.accuracy_metrics.precision,
        "recall": result.accuracy_metrics.recall,
        "calibration_error": result.accuracy_metrics.calibration_error,
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "max_drawdown": result.max_drawdown,
        "expected_value": result.expected_value,
    }


def generate_periodic_report(
    period_start: datetime, period_end: datetime, window: RollingWindow, model_analyses: List[ModelAnalysisResult],
) -> dict:
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "window": window.value,
        "engines": [_model_analysis_summary(result) for result in model_analyses],
    }


def generate_benchmark_report(benchmark: BenchmarkResult) -> dict:
    return {
        "subject_type": benchmark.subject_type.value,
        "subject_a": benchmark.subject_a,
        "subject_b": benchmark.subject_b,
        "window": benchmark.window.value,
        "metrics_a": benchmark.metrics_a,
        "metrics_b": benchmark.metrics_b,
        "p_value": benchmark.p_value,
        "significant": benchmark.significant,
    }


def generate_experiment_summary(
    experiment: Experiment,
    hypothesis: Optional[Hypothesis],
    backtest_results: List[BacktestResult],
    benchmark_results: List[BenchmarkResult],
) -> dict:
    return {
        "experiment_id": experiment.id,
        "name": experiment.name,
        "description": experiment.description,
        "author": experiment.author,
        "status": experiment.status.value,
        "hypothesis": {
            "statement": hypothesis.statement,
            "outcome": hypothesis.outcome.value if hypothesis.outcome else None,
            "evidence": hypothesis.evidence,
        } if hypothesis is not None else None,
        "backtests": [
            {
                "method": result.method.value, "engine_name": result.engine_name,
                "engine_version": result.engine_version, "sample_count": result.sample_count,
                "aggregate_sharpe": result.aggregate_sharpe, "aggregate_sortino": result.aggregate_sortino,
                "aggregate_max_drawdown": result.aggregate_max_drawdown,
                "aggregate_win_rate": result.aggregate_win_rate,
                "aggregate_expected_value": result.aggregate_expected_value,
            }
            for result in backtest_results
        ],
        "benchmarks": [generate_benchmark_report(result) for result in benchmark_results],
    }
