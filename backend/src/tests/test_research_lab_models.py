"""Tests for research_lab/models.py."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from learning.models import AccuracyMetrics, RollingWindow
from research_lab.models import (
    BacktestMethod,
    BacktestResult,
    BenchmarkResult,
    BenchmarkSubjectType,
    DatasetDefinition,
    Experiment,
    ExperimentStatus,
    FeatureCorrelationRecord,
    FeatureDriftRecord,
    FeatureImportanceRecord,
    FeatureStabilityRecord,
    FoldResult,
    Hypothesis,
    HypothesisOutcome,
    ModelAnalysisResult,
    PromotionDecision,
    PromotionRecommendation,
    Report,
    ReportType,
)


def test_experiment_defaults_to_draft():
    experiment = Experiment(name="Test", author="claude")
    assert experiment.status == ExperimentStatus.DRAFT
    assert experiment.id is None


def test_experiment_rejects_blank_name():
    with pytest.raises(ValidationError):
        Experiment(name="   ", author="claude")


def test_hypothesis_rejects_blank_statement():
    with pytest.raises(ValidationError):
        Hypothesis(statement="")


def test_hypothesis_outcome_defaults_to_none():
    hypothesis = Hypothesis(statement="Momentum improves precision")
    assert hypothesis.outcome is None
    assert hypothesis.resolved_at is None


def test_fold_result_requires_nonnegative_max_drawdown():
    with pytest.raises(ValidationError):
        FoldResult(
            fold_index=0, test_start=datetime.now(timezone.utc), test_end=datetime.now(timezone.utc),
            sample_count=5, total_return=1.0, sharpe_ratio=0.5, sortino_ratio=0.5,
            max_drawdown=-1.0, win_rate=0.6, expected_value=1.0,
        )


def test_backtest_result_defaults_to_empty_folds():
    result = BacktestResult(
        method=BacktestMethod.WALK_FORWARD, engine_name="E", engine_version="v1",
        window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc),
    )
    assert result.folds == []
    assert result.sample_count == 0


def test_benchmark_result_p_value_bounded():
    with pytest.raises(ValidationError):
        BenchmarkResult(
            subject_type=BenchmarkSubjectType.ENGINE_VERSION, subject_a="v1", subject_b="v2",
            window=RollingWindow.LIFETIME, p_value=1.5, significant=False,
        )


def test_feature_correlation_record_bounded_to_valid_range():
    with pytest.raises(ValidationError):
        FeatureCorrelationRecord(
            symbol="AAPL", feature_a="a", feature_b="b", correlation=1.5, sample_count=10,
            window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc),
        )


def test_feature_stability_record_construction():
    record = FeatureStabilityRecord(
        symbol="AAPL", feature_name="rsi_14", stability_score=0.9, coefficient_of_variation=0.1,
        sample_count=20, window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc),
    )
    assert record.stability_score == 0.9


def test_feature_drift_record_construction():
    now = datetime.now(timezone.utc)
    record = FeatureDriftRecord(
        symbol="AAPL", feature_name="rsi_14", drift_statistic=0.8, p_value=0.001, drifted=True,
        baseline_window_start=now, baseline_window_end=now, recent_window_start=now, recent_window_end=now,
    )
    assert record.drifted is True


def test_feature_importance_record_bounded():
    with pytest.raises(ValidationError):
        FeatureImportanceRecord(symbol="AAPL", engine_name="E", feature_name="f", importance=1.5)


def test_model_analysis_result_embeds_accuracy_metrics():
    accuracy_metrics = AccuracyMetrics(
        engine_name="E", engine_version="v1", window=RollingWindow.LIFETIME, sample_count=10,
        accuracy=0.7, precision=0.6, recall=0.6, calibration_error=0.1, confidence_reliability=0.9,
        expected_return_error=1.0, volatility_error=2.0,
    )
    result = ModelAnalysisResult(
        engine_name="E", engine_version="v1", window=RollingWindow.LIFETIME, accuracy_metrics=accuracy_metrics,
        sharpe_ratio=1.0, sortino_ratio=1.2, max_drawdown=5.0, expected_value=2.0,
    )
    assert result.accuracy_metrics.accuracy == 0.7


def test_promotion_decision_construction():
    decision = PromotionDecision(
        engine_name="E", candidate_version="v2", live_version="v1",
        recommendation=PromotionRecommendation.PROMOTE, rationale="better accuracy",
        window=RollingWindow.THIRTY_DAY, candidate_accuracy=0.7, live_accuracy=0.6, candidate_sample_count=25,
    )
    assert decision.recommendation == PromotionRecommendation.PROMOTE


def test_dataset_definition_rejects_blank_name():
    with pytest.raises(ValidationError):
        DatasetDefinition(
            name="  ", symbols=["AAPL"], feature_names=["rsi_14"],
            start=datetime.now(timezone.utc), end=datetime.now(timezone.utc),
        )


def test_report_defaults_to_empty_content():
    report = Report(report_type=ReportType.WEEKLY, title="Weekly Report")
    assert report.content == {}
