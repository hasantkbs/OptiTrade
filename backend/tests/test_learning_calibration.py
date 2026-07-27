"""Tests for learning/calibration.py."""
from datetime import datetime, timezone

from decision_engine.models import Prediction
from learning import calibration
from learning.models import EngineOutcomeRecord, SampleSource


def _outcome(confidence: float, correct: bool) -> EngineOutcomeRecord:
    return EngineOutcomeRecord(
        sample_id=1, engine_name="E", engine_version="v1", symbol="AAPL", source=SampleSource.LIVE,
        prediction=Prediction.BUY, confidence=confidence, expected_return=2.0, expected_volatility=15.0,
        decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5, evaluated=True,
        evaluated_at=datetime.now(timezone.utc), actual_return=2.0, actual_volatility=12.0, correct=correct,
    )


def test_ece_zero_for_no_outcomes():
    assert calibration.expected_calibration_error([]) == 0.0


def test_ece_zero_when_perfectly_calibrated():
    # confidence 1.0 bucket, all correct -> bucket accuracy 1.0 == bucket avg confidence 1.0
    outcomes = [_outcome(1.0, True) for _ in range(5)]
    assert calibration.expected_calibration_error(outcomes) == 0.0


def test_ece_high_when_overconfident_and_wrong():
    outcomes = [_outcome(0.95, False) for _ in range(5)]
    ece = calibration.expected_calibration_error(outcomes)
    assert ece > 0.9


def test_ece_ignores_unevaluated_outcomes():
    unevaluated = EngineOutcomeRecord(
        sample_id=1, engine_name="E", engine_version="v1", symbol="AAPL", source=SampleSource.LIVE,
        prediction=Prediction.BUY, confidence=0.9, expected_return=2.0, expected_volatility=15.0,
        decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5,
    )
    assert calibration.expected_calibration_error([unevaluated]) == 0.0


def test_confidence_reliability_is_inverse_of_ece():
    outcomes = [_outcome(0.95, False) for _ in range(5)]
    ece = calibration.expected_calibration_error(outcomes)
    reliability = calibration.confidence_reliability_score(outcomes)
    assert reliability == 1.0 - ece


def test_confidence_reliability_bounded_between_zero_and_one():
    outcomes = [_outcome(c / 10, c % 2 == 0) for c in range(1, 10)]
    reliability = calibration.confidence_reliability_score(outcomes)
    assert 0.0 <= reliability <= 1.0
