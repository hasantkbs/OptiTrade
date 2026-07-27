"""
OptiTrade Continuous Learning — facade.

The single public entry point every future caller (a scheduled job, a
future admin/monitoring endpoint, or the Decision Engine's own shadow-
evaluation hook) should depend on. Ties together the tracker,
evaluator, accuracy/calibration computation, weighting, drift
detection, and scheduler behind one dependency-injectable object -
mirroring the facade pattern established by
`feature_store.service.FeatureStoreService` and
`decision_engine.service.DecisionEngine`.

Never predicts, never votes - every method here either records an
observation or reads back already-computed statistics.
"""
from __future__ import annotations

from typing import List, Optional

from decision_engine.interfaces import VotingEngineProtocol
from decision_engine.models import DecisionOutput
from engine_registry.registry import EngineRegistry, default_registry
from learning.config import LearningConfig
from learning.drift import DriftDetector
from learning.evaluator import OutcomeEvaluator
from learning.models import (
    AccuracyMetrics,
    DriftSignal,
    LearningSample,
    PromotionCandidate,
    RollingWindow,
    WeightUpdate,
)
from learning.persistence import LearningRepository
from learning.scheduler import LearningCycleResult, LearningScheduler
from learning.tracker import SampleTracker
from learning.weighting import WeightCalculator


class LearningService:
    """Dependency-injectable facade over the whole Continuous Learning
    system."""

    def __init__(
        self,
        repository: Optional[LearningRepository] = None,
        tracker: Optional[SampleTracker] = None,
        evaluator: Optional[OutcomeEvaluator] = None,
        weight_calculator: Optional[WeightCalculator] = None,
        drift_detector: Optional[DriftDetector] = None,
        scheduler: Optional[LearningScheduler] = None,
        engine_registry: Optional[EngineRegistry] = None,
        config: Optional[LearningConfig] = None,
    ) -> None:
        self.config = config or LearningConfig.from_env()
        self.repository = repository or LearningRepository()
        self.tracker = tracker or SampleTracker(repository=self.repository, config=self.config)
        self.evaluator = evaluator or OutcomeEvaluator(repository=self.repository, config=self.config)
        self.weight_calculator = weight_calculator or WeightCalculator(repository=self.repository, config=self.config)
        self.drift_detector = drift_detector or DriftDetector(config=self.config)
        self.scheduler = scheduler or LearningScheduler(
            repository=self.repository, evaluator=self.evaluator,
            weight_calculator=self.weight_calculator, drift_detector=self.drift_detector, config=self.config,
        )
        self.engine_registry = engine_registry or default_registry

    # ── Tracking (observation only) ─────────────────────────────────────

    def record_decision(self, output: DecisionOutput) -> LearningSample:
        """Records a live, already-final `DecisionOutput`. Never
        influences it - purely observes."""
        return self.tracker.track_decision(output)

    def record_shadow_vote(self, engine: VotingEngineProtocol, symbol: str) -> LearningSample:
        """Records one shadow engine's vote, collected outside of any
        live decision - never affects live decisions."""
        return self.tracker.track_shadow_vote(engine, symbol)

    # ── Learning cycle ───────────────────────────────────────────────────

    def run_learning_cycle(self, now=None) -> LearningCycleResult:
        """Evaluates pending samples, recomputes accuracy/drift/weights
        for every observed engine. Intended to be invoked periodically
        by an external scheduler."""
        return self.scheduler.run_once(now)

    # ── Read-back ────────────────────────────────────────────────────────

    def get_accuracy(self, engine_name: str, engine_version: str, window: RollingWindow) -> Optional[AccuracyMetrics]:
        return self.repository.get_latest_accuracy(engine_name, engine_version, window)

    def get_accuracy_history(
        self, engine_name: str, engine_version: str, window: RollingWindow, limit: int = 10,
    ) -> List[AccuracyMetrics]:
        return self.repository.get_accuracy_history(engine_name, engine_version, window, limit)

    def get_weight_history(self, engine_name: str, engine_version: str, limit: int = 10) -> List[WeightUpdate]:
        return self.repository.get_weight_update_history(engine_name, engine_version, limit)

    def get_drift_signals(self, engine_name: str, engine_version: str, limit: int = 10) -> List[DriftSignal]:
        return self.repository.get_recent_drift_signals(engine_name, engine_version, limit)

    # ── Version history / promotion ─────────────────────────────────────

    def version_history(
        self, engine_name: str, window: RollingWindow = RollingWindow.LIFETIME,
    ) -> dict:
        """Every registered version of `engine_name` (per the Engine
        Registry) paired with its latest accuracy snapshot for
        `window`, wherever one has been computed."""
        history = {}
        for version in self.engine_registry.versions_of(engine_name):
            metrics = self.repository.get_latest_accuracy(engine_name, version, window)
            if metrics is not None:
                history[version] = metrics
        return history

    def promotion_candidates(
        self, engine_name: str, live_version: str, window: RollingWindow = RollingWindow.THIRTY_DAY,
    ) -> List[PromotionCandidate]:
        """Every OTHER registered version of `engine_name` (e.g. a
        shadow engine, or a newer not-yet-promoted version) whose
        accuracy over `window` exceeds the currently-live version's by
        at least `config.promotion_margin`, with enough evaluated
        samples to be meaningful. A recommendation only - never an
        automatic promotion."""
        live_metrics = self.repository.get_latest_accuracy(engine_name, live_version, window)
        live_accuracy = live_metrics.accuracy if live_metrics is not None else 0.0

        candidates: List[PromotionCandidate] = []
        for version in self.engine_registry.versions_of(engine_name):
            if version == live_version:
                continue
            metrics = self.repository.get_latest_accuracy(engine_name, version, window)
            if metrics is None or metrics.sample_count < self.config.min_samples_for_promotion:
                continue
            if metrics.accuracy >= live_accuracy + self.config.promotion_margin:
                candidates.append(
                    PromotionCandidate(
                        engine_name=engine_name, candidate_version=version, live_version=live_version,
                        window=window, candidate_accuracy=metrics.accuracy, live_accuracy=live_accuracy,
                        candidate_sample_count=metrics.sample_count,
                    )
                )
        return candidates
