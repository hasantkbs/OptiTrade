"""
OptiTrade Continuous Learning — drift detection.

Classifies one engine as DEGRADING, IMPROVING, UNSTABLE, or STABLE by
comparing a recent-window accuracy snapshot against a longer baseline
window, plus an instability check across every available window's
accuracy (a large spread across 7d/30d/90d means the engine's
performance is erratic even if it isn't clearly trending in either
direction).
"""
from __future__ import annotations

import logging
import statistics
from typing import Dict, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from learning.config import LearningConfig
from learning.models import AccuracyMetrics, DriftSignal, DriftType, RollingWindow

logger = logging.getLogger(__name__)


class DriftDetector:
    """Compares per-window `AccuracyMetrics` snapshots for one engine
    and classifies its trend. Never predicts anything itself - purely
    a statistical comparison of already-computed accuracy."""

    def __init__(self, config: Optional[LearningConfig] = None) -> None:
        self.config = config or LearningConfig.from_env()

    def detect(
        self,
        engine_name: str,
        engine_version: str,
        metrics_by_window: Dict[RollingWindow, AccuracyMetrics],
    ) -> DriftSignal:
        recent_window = RollingWindow(self.config.drift_recent_window)
        baseline_window = RollingWindow(self.config.drift_baseline_window)
        recent = metrics_by_window.get(recent_window)
        baseline = metrics_by_window.get(baseline_window)

        if (
            recent is None or baseline is None
            or recent.sample_count < self.config.min_samples_for_drift
            or baseline.sample_count < self.config.min_samples_for_drift
        ):
            return self._signal(
                engine_name, engine_version, DriftType.STABLE, 0.0, recent_window, baseline_window,
                "insufficient evaluated samples for drift detection",
            )

        delta = recent.accuracy - baseline.accuracy
        variance = self._variance(metrics_by_window)

        if variance is not None and variance > self.config.drift_unstable_variance_threshold:
            return self._signal(
                engine_name, engine_version, DriftType.UNSTABLE, variance, recent_window, baseline_window,
                f"accuracy variance {variance:.4f} across windows exceeds threshold "
                f"{self.config.drift_unstable_variance_threshold}",
            )

        if delta > self.config.drift_improve_threshold:
            return self._signal(
                engine_name, engine_version, DriftType.IMPROVING, delta, recent_window, baseline_window,
                f"recent ({recent_window.value}) accuracy {recent.accuracy:.3f} exceeds baseline "
                f"({baseline_window.value}) accuracy {baseline.accuracy:.3f} by {delta:.3f}",
            )

        if delta < -self.config.drift_degrade_threshold:
            return self._signal(
                engine_name, engine_version, DriftType.DEGRADING, abs(delta), recent_window, baseline_window,
                f"recent ({recent_window.value}) accuracy {recent.accuracy:.3f} is below baseline "
                f"({baseline_window.value}) accuracy {baseline.accuracy:.3f} by {abs(delta):.3f}",
            )

        return self._signal(
            engine_name, engine_version, DriftType.STABLE, abs(delta), recent_window, baseline_window,
            f"recent ({recent_window.value}) accuracy {recent.accuracy:.3f} is within threshold of baseline "
            f"({baseline_window.value}) accuracy {baseline.accuracy:.3f}",
        )

    def _variance(self, metrics_by_window: Dict[RollingWindow, AccuracyMetrics]) -> Optional[float]:
        accuracies = [
            metrics.accuracy for metrics in metrics_by_window.values()
            if metrics.sample_count >= self.config.min_samples_for_drift
        ]
        if len(accuracies) < 2:
            return None
        return statistics.pvariance(accuracies)

    def _signal(
        self, engine_name: str, engine_version: str, drift_type: DriftType, magnitude: float,
        recent_window: RollingWindow, baseline_window: RollingWindow, evidence: str,
    ) -> DriftSignal:
        signal = DriftSignal(
            engine_name=engine_name, engine_version=engine_version, drift_type=drift_type,
            magnitude=magnitude, recent_window=recent_window, baseline_window=baseline_window,
            evidence=evidence,
        )
        log_event(
            logger, component="learning", module="learning.drift", operation="detect",
            status=STATUS_SUCCESS, engine_name=engine_name, engine_version=engine_version,
            drift_type=drift_type.value, magnitude=magnitude,
        )
        return signal
