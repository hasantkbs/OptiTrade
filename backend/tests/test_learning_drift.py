"""Tests for learning/drift.py."""
from learning.config import LearningConfig
from learning.drift import DriftDetector
from learning.models import AccuracyMetrics, DriftType, RollingWindow


def _metrics(window: RollingWindow, accuracy: float, sample_count: int = 20) -> AccuracyMetrics:
    return AccuracyMetrics(
        engine_name="E", engine_version="v1", window=window, sample_count=sample_count,
        accuracy=accuracy, precision=accuracy, recall=accuracy, calibration_error=0.1,
        confidence_reliability=0.9, expected_return_error=1.0, volatility_error=2.0,
    )


def test_insufficient_samples_returns_stable_with_zero_magnitude():
    config = LearningConfig(min_samples_for_drift=10)
    detector = DriftDetector(config=config)
    metrics_by_window = {
        RollingWindow.SEVEN_DAY: _metrics(RollingWindow.SEVEN_DAY, 0.5, sample_count=2),
        RollingWindow.THIRTY_DAY: _metrics(RollingWindow.THIRTY_DAY, 0.5, sample_count=2),
    }
    signal = detector.detect("E", "v1", metrics_by_window)
    assert signal.drift_type == DriftType.STABLE
    assert signal.magnitude == 0.0


def test_improving_when_recent_accuracy_exceeds_baseline_by_threshold():
    config = LearningConfig(drift_improve_threshold=0.05, drift_unstable_variance_threshold=1.0)
    detector = DriftDetector(config=config)
    metrics_by_window = {
        RollingWindow.SEVEN_DAY: _metrics(RollingWindow.SEVEN_DAY, 0.8),
        RollingWindow.THIRTY_DAY: _metrics(RollingWindow.THIRTY_DAY, 0.6),
    }
    signal = detector.detect("E", "v1", metrics_by_window)
    assert signal.drift_type == DriftType.IMPROVING
    assert signal.magnitude > 0


def test_degrading_when_recent_accuracy_below_baseline_by_threshold():
    config = LearningConfig(drift_degrade_threshold=0.05, drift_unstable_variance_threshold=1.0)
    detector = DriftDetector(config=config)
    metrics_by_window = {
        RollingWindow.SEVEN_DAY: _metrics(RollingWindow.SEVEN_DAY, 0.4),
        RollingWindow.THIRTY_DAY: _metrics(RollingWindow.THIRTY_DAY, 0.7),
    }
    signal = detector.detect("E", "v1", metrics_by_window)
    assert signal.drift_type == DriftType.DEGRADING


def test_stable_when_delta_within_thresholds():
    config = LearningConfig(drift_improve_threshold=0.1, drift_degrade_threshold=0.1, drift_unstable_variance_threshold=1.0)
    detector = DriftDetector(config=config)
    metrics_by_window = {
        RollingWindow.SEVEN_DAY: _metrics(RollingWindow.SEVEN_DAY, 0.62),
        RollingWindow.THIRTY_DAY: _metrics(RollingWindow.THIRTY_DAY, 0.6),
    }
    signal = detector.detect("E", "v1", metrics_by_window)
    assert signal.drift_type == DriftType.STABLE


def test_unstable_when_variance_across_windows_exceeds_threshold():
    config = LearningConfig(drift_unstable_variance_threshold=0.01, drift_improve_threshold=0.5, drift_degrade_threshold=0.5)
    detector = DriftDetector(config=config)
    metrics_by_window = {
        RollingWindow.SEVEN_DAY: _metrics(RollingWindow.SEVEN_DAY, 0.3),
        RollingWindow.THIRTY_DAY: _metrics(RollingWindow.THIRTY_DAY, 0.6),
        RollingWindow.NINETY_DAY: _metrics(RollingWindow.NINETY_DAY, 0.9),
    }
    signal = detector.detect("E", "v1", metrics_by_window)
    assert signal.drift_type == DriftType.UNSTABLE


def test_missing_window_metrics_returns_stable():
    detector = DriftDetector()
    signal = detector.detect("E", "v1", {})
    assert signal.drift_type == DriftType.STABLE


def test_variance_returns_none_with_fewer_than_two_sufficient_windows():
    config = LearningConfig(min_samples_for_drift=10)
    detector = DriftDetector(config=config)
    metrics_by_window = {RollingWindow.SEVEN_DAY: _metrics(RollingWindow.SEVEN_DAY, 0.5, sample_count=20)}
    assert detector._variance(metrics_by_window) is None


def test_uses_configured_recent_and_baseline_windows():
    config = LearningConfig(drift_recent_window="30d", drift_baseline_window="90d", drift_unstable_variance_threshold=1.0)
    detector = DriftDetector(config=config)
    metrics_by_window = {
        RollingWindow.THIRTY_DAY: _metrics(RollingWindow.THIRTY_DAY, 0.9),
        RollingWindow.NINETY_DAY: _metrics(RollingWindow.NINETY_DAY, 0.5),
    }
    signal = detector.detect("E", "v1", metrics_by_window)
    assert signal.recent_window == RollingWindow.THIRTY_DAY
    assert signal.baseline_window == RollingWindow.NINETY_DAY
    assert signal.drift_type == DriftType.IMPROVING
