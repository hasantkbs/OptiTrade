"""
OptiTrade Continuous Learning — cycle orchestration.

`LearningScheduler.run_once()` is the single entry point that ties
evaluation, accuracy computation, drift detection, and weighting
together into one pass: evaluate every pending sample, then for each
engine seen in the outcome history, recompute accuracy for every
rolling window, detect drift, and recompute its weight.

This module does NOT itself run a background thread/cron loop - it is
the orchestration logic an external scheduler (a cron job, Celery beat,
a simple periodic task runner wired up in a later integration step)
calls on each tick. Deliberately out of scope here per
"do not integrate endpoints yet."
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from learning import accuracy
from learning.config import LearningConfig
from learning.drift import DriftDetector
from learning.evaluator import OutcomeEvaluator
from learning.models import AccuracyMetrics, DriftSignal, RollingWindow, WeightUpdate
from learning.persistence import LearningRepository
from learning.weighting import WeightCalculator

logger = logging.getLogger(__name__)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class LearningCycleResult:
    """Summary of one `run_once()` pass."""

    evaluated_count: int
    engines_processed: int
    accuracy_snapshots: Dict[Tuple[str, str], Dict[RollingWindow, AccuracyMetrics]] = field(default_factory=dict)
    drift_signals: List[DriftSignal] = field(default_factory=list)
    weight_updates: List[WeightUpdate] = field(default_factory=list)


class LearningScheduler:
    """Orchestrates one full learning cycle. Never predicts, never
    votes - purely coordinates the other learning modules."""

    def __init__(
        self,
        repository: Optional[LearningRepository] = None,
        evaluator: Optional[OutcomeEvaluator] = None,
        weight_calculator: Optional[WeightCalculator] = None,
        drift_detector: Optional[DriftDetector] = None,
        config: Optional[LearningConfig] = None,
    ) -> None:
        self.config = config or LearningConfig.from_env()
        self.repository = repository or LearningRepository()
        self.evaluator = evaluator or OutcomeEvaluator(repository=self.repository, config=self.config)
        self.weight_calculator = weight_calculator or WeightCalculator(repository=self.repository, config=self.config)
        self.drift_detector = drift_detector or DriftDetector(config=self.config)

    def run_once(self, now: Optional[datetime] = None) -> LearningCycleResult:
        started_at = time.perf_counter()
        now = now or datetime.now(timezone.utc)

        evaluated_count = self.evaluator.evaluate_pending(now)
        engines = self.repository.distinct_engines()

        accuracy_snapshots: Dict[Tuple[str, str], Dict[RollingWindow, AccuracyMetrics]] = {}
        drift_signals: List[DriftSignal] = []
        weight_updates: List[WeightUpdate] = []

        # Each engine is isolated - a bad accuracy computation, drift
        # detection, or weight recompute for one engine is logged and
        # skipped rather than aborting the rest of the cycle (every
        # other already-registered engine still gets its accuracy/
        # drift/weight refreshed this pass).
        for engine_name, engine_version in engines:
            try:
                metrics_by_window = self._compute_all_windows(engine_name, engine_version, now)
                accuracy_snapshots[(engine_name, engine_version)] = metrics_by_window

                drift_signal = self.drift_detector.detect(engine_name, engine_version, metrics_by_window)
                self.repository.save_drift_signal(drift_signal)
                drift_signals.append(drift_signal)

                weighting_window = RollingWindow(self.config.weighting_window)
                weighting_outcomes = self.repository.get_engine_outcomes(
                    engine_name, engine_version,
                    since=accuracy.window_start(weighting_window, now) or _EPOCH,
                    only_evaluated=True,
                )
                weight_update = self.weight_calculator.recompute_weight(engine_name, engine_version, weighting_outcomes)
                weight_updates.append(weight_update)
            except Exception as exc:
                log_event(
                    logger, component="learning", module="learning.scheduler", operation="run_once_engine",
                    status=STATUS_ERROR, engine_name=engine_name, engine_version=engine_version,
                    error_type=type(exc).__name__, level=logging.ERROR,
                )

        log_event(
            logger, component="learning", module="learning.scheduler", operation="run_once",
            status=STATUS_SUCCESS, evaluated_count=evaluated_count, engines_processed=len(engines),
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return LearningCycleResult(
            evaluated_count=evaluated_count, engines_processed=len(engines),
            accuracy_snapshots=accuracy_snapshots, drift_signals=drift_signals, weight_updates=weight_updates,
        )

    def _compute_all_windows(
        self, engine_name: str, engine_version: str, now: datetime,
    ) -> Dict[RollingWindow, AccuracyMetrics]:
        metrics_by_window: Dict[RollingWindow, AccuracyMetrics] = {}
        for window in RollingWindow:
            since = accuracy.window_start(window, now) or _EPOCH
            outcomes = self.repository.get_engine_outcomes(engine_name, engine_version, since=since, only_evaluated=True)
            metrics = accuracy.compute_accuracy_metrics(engine_name, engine_version, window, outcomes, self.config)
            self.repository.save_accuracy_metrics(metrics)
            metrics_by_window[window] = metrics
        return metrics_by_window
