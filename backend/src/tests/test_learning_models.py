"""Tests for learning/models.py."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from decision_engine.models import EngineVote, Prediction
from learning.models import (
    AccuracyMetrics,
    DriftSignal,
    DriftType,
    EngineOutcomeRecord,
    LearningSample,
    PromotionCandidate,
    RollingWindow,
    SampleSource,
    WeightingPolicy,
    WeightUpdate,
)


def _vote() -> EngineVote:
    return EngineVote(
        engine_name="E", engine_version="v1", prediction=Prediction.BUY,
        confidence=0.7, expected_return=2.0, volatility=15.0, evidence=["e"],
    )


def test_learning_sample_defaults():
    sample = LearningSample(
        symbol="AAPL", source=SampleSource.LIVE, decision=Prediction.BUY, confidence=0.7,
        expected_return=2.0, expected_volatility=15.0, engine_results=[_vote()],
        decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5,
    )
    assert sample.id is None
    assert sample.evaluated is False
    assert sample.evaluated_at is None
    assert len(sample.engine_results) == 1


def test_learning_sample_rejects_blank_symbol():
    with pytest.raises(ValidationError):
        LearningSample(
            symbol="  ", source=SampleSource.LIVE, decision=Prediction.HOLD, confidence=0.0,
            expected_return=0.0, expected_volatility=15.0,
            decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5,
        )


def test_learning_sample_rejects_non_positive_horizon():
    with pytest.raises(ValidationError):
        LearningSample(
            symbol="AAPL", source=SampleSource.LIVE, decision=Prediction.HOLD, confidence=0.0,
            expected_return=0.0, expected_volatility=15.0,
            decided_at=datetime.now(timezone.utc), evaluation_horizon_days=0,
        )


def test_engine_outcome_record_defaults_unevaluated():
    outcome = EngineOutcomeRecord(
        sample_id=1, engine_name="E", engine_version="v1", symbol="AAPL", source=SampleSource.LIVE,
        prediction=Prediction.BUY, confidence=0.7, expected_return=2.0, expected_volatility=15.0,
        decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5,
    )
    assert outcome.evaluated is False
    assert outcome.correct is None


def test_accuracy_metrics_bounds_enforced():
    with pytest.raises(ValidationError):
        AccuracyMetrics(
            engine_name="E", engine_version="v1", window=RollingWindow.SEVEN_DAY, sample_count=1,
            accuracy=1.5, precision=0.5, recall=0.5, calibration_error=0.1,
            confidence_reliability=0.9, expected_return_error=1.0, volatility_error=1.0,
        )


def test_weight_update_requires_policy_enum():
    update = WeightUpdate(
        engine_name="E", engine_version="v1", old_weight=1.0, new_weight=1.1,
        policy=WeightingPolicy.BAYESIAN, reason="test",
    )
    assert update.policy == WeightingPolicy.BAYESIAN


def test_drift_signal_magnitude_must_be_nonnegative():
    with pytest.raises(ValidationError):
        DriftSignal(
            engine_name="E", engine_version="v1", drift_type=DriftType.DEGRADING, magnitude=-0.1,
            recent_window=RollingWindow.SEVEN_DAY, baseline_window=RollingWindow.THIRTY_DAY, evidence="x",
        )


def test_promotion_candidate_construction():
    candidate = PromotionCandidate(
        engine_name="E", candidate_version="v2", live_version="v1", window=RollingWindow.THIRTY_DAY,
        candidate_accuracy=0.7, live_accuracy=0.6, candidate_sample_count=25,
    )
    assert candidate.candidate_accuracy > candidate.live_accuracy
