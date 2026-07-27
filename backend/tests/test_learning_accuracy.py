"""Tests for learning/accuracy.py."""
from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.models import Prediction
from learning import accuracy
from learning.config import LearningConfig
from learning.models import EngineOutcomeRecord, RollingWindow, SampleSource


def _outcome(prediction: Prediction, actual_return: float, correct: bool, evaluated: bool = True) -> EngineOutcomeRecord:
    return EngineOutcomeRecord(
        sample_id=1, engine_name="E", engine_version="v1", symbol="AAPL", source=SampleSource.LIVE,
        prediction=prediction, confidence=0.7, expected_return=2.0, expected_volatility=15.0,
        decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5, evaluated=evaluated,
        evaluated_at=datetime.now(timezone.utc) if evaluated else None,
        actual_return=actual_return if evaluated else None,
        actual_volatility=12.0 if evaluated else None, correct=correct if evaluated else None,
    )


def test_window_start_for_seven_day():
    now = datetime.now(timezone.utc)
    start = accuracy.window_start(RollingWindow.SEVEN_DAY, now)
    assert start == now - timedelta(days=7)


def test_window_start_lifetime_is_none():
    assert accuracy.window_start(RollingWindow.LIFETIME, datetime.now(timezone.utc)) is None


def test_compute_accuracy_metrics_with_no_outcomes_returns_zeroed_metrics():
    metrics = accuracy.compute_accuracy_metrics("E", "v1", RollingWindow.SEVEN_DAY, [])
    assert metrics.sample_count == 0
    assert metrics.accuracy == 0.0
    assert metrics.confidence_reliability == 1.0


def test_compute_accuracy_metrics_ignores_unevaluated_outcomes():
    outcomes = [_outcome(Prediction.BUY, 2.0, True, evaluated=False)]
    metrics = accuracy.compute_accuracy_metrics("E", "v1", RollingWindow.SEVEN_DAY, outcomes)
    assert metrics.sample_count == 0


def test_compute_accuracy_metrics_all_correct():
    outcomes = [_outcome(Prediction.BUY, 2.0, True) for _ in range(5)]
    metrics = accuracy.compute_accuracy_metrics("E", "v1", RollingWindow.SEVEN_DAY, outcomes)
    assert metrics.sample_count == 5
    assert metrics.accuracy == 1.0


def test_compute_accuracy_metrics_mixed_correctness():
    outcomes = [_outcome(Prediction.BUY, 2.0, True), _outcome(Prediction.BUY, -2.0, False)]
    metrics = accuracy.compute_accuracy_metrics("E", "v1", RollingWindow.SEVEN_DAY, outcomes)
    assert metrics.accuracy == 0.5


def test_compute_accuracy_metrics_expected_return_error_is_mean_absolute_error():
    outcomes = [_outcome(Prediction.BUY, actual_return=5.0, correct=True)]  # expected_return=2.0 in helper
    metrics = accuracy.compute_accuracy_metrics("E", "v1", RollingWindow.SEVEN_DAY, outcomes)
    assert metrics.expected_return_error == pytest.approx(3.0)


def test_compute_accuracy_metrics_volatility_error_is_mean_absolute_error():
    outcomes = [_outcome(Prediction.BUY, actual_return=2.0, correct=True)]  # expected_vol 15, actual_vol 12
    metrics = accuracy.compute_accuracy_metrics("E", "v1", RollingWindow.SEVEN_DAY, outcomes)
    assert metrics.volatility_error == pytest.approx(3.0)


def test_compute_accuracy_metrics_uses_configured_hold_band():
    config = LearningConfig(hold_band_pct=4.0)
    # actual_return=1.0 is within +-2.0 band -> counted as HOLD label for precision/recall purposes.
    # Macro precision/recall averages across all 3 classes (BUY/HOLD/SELL); with only a HOLD
    # sample present, HOLD scores 1.0 and the two absent classes score 0 (zero_division=0),
    # so macro = (1 + 0 + 0) / 3.
    outcomes = [_outcome(Prediction.HOLD, actual_return=1.0, correct=True)]
    metrics = accuracy.compute_accuracy_metrics("E", "v1", RollingWindow.SEVEN_DAY, outcomes, config=config)
    assert metrics.precision == pytest.approx(1 / 3)
    assert metrics.recall == pytest.approx(1 / 3)
