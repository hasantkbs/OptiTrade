"""
OptiTrade Continuous Learning — engine weight computation.

This is the write side of "Decision Engine reads weights, Learning
writes weights": `decision_engine.weighting.AccuracyWeightProvider`
already reads each engine's weight from the Feature Store as
`(engine_name, DecisionEngineConfig.accuracy_feature_name)` - this
module is what actually computes and writes that value.

Three configurable policies (`exponential_decay`, `rolling_average`,
`bayesian`) each compute a *target* weight from recent accuracy; all
three are then passed through the same hard step-cap
(`LearningConfig.max_weight_step`) before being applied, so a weight
can never jump more than that cap in one update regardless of which
policy produced the target - satisfying "weights must never change
abruptly" uniformly across policies.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.config import DecisionEngineConfig
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from learning.config import LearningConfig
from learning.models import EngineOutcomeRecord, WeightingPolicy, WeightUpdate
from learning.persistence import LearningRepository

logger = logging.getLogger(__name__)


class WeightCalculator:
    """Computes and persists one engine's updated accuracy weight."""

    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        repository: Optional[LearningRepository] = None,
        config: Optional[LearningConfig] = None,
        decision_engine_config: Optional[DecisionEngineConfig] = None,
    ) -> None:
        self.feature_store = feature_store or get_default_feature_store_service()
        self.repository = repository or LearningRepository()
        self.config = config or LearningConfig.from_env()
        self._decision_engine_config = decision_engine_config or DecisionEngineConfig.from_env()

    def recompute_weight(
        self,
        engine_name: str,
        engine_version: str,
        outcomes: List[EngineOutcomeRecord],
        policy: Optional[WeightingPolicy] = None,
    ) -> WeightUpdate:
        started_at = time.perf_counter()
        policy = policy or self.config.weighting_policy
        evaluated = [o for o in outcomes if o.evaluated and o.correct is not None]
        old_weight = self._current_weight(engine_name)

        if len(evaluated) < self.config.min_samples_for_weighting:
            update = WeightUpdate(
                engine_name=engine_name, engine_version=engine_version,
                old_weight=old_weight, new_weight=old_weight, policy=policy,
                reason=(
                    f"insufficient evaluated samples ({len(evaluated)} < "
                    f"{self.config.min_samples_for_weighting}) - weight unchanged"
                ),
            )
            self.repository.save_weight_update(update)
            return update

        if policy == WeightingPolicy.EXPONENTIAL_DECAY:
            target, reason = self._exponential_decay_target(evaluated, old_weight)
        elif policy == WeightingPolicy.ROLLING_AVERAGE:
            target, reason = self._rolling_average_target(evaluated)
        elif policy == WeightingPolicy.BAYESIAN:
            target, reason = self._bayesian_target(evaluated)
        else:
            raise ValueError(f"unknown weighting policy: {policy}")

        new_weight = self._apply_step_cap(old_weight, target)
        update = WeightUpdate(
            engine_name=engine_name, engine_version=engine_version,
            old_weight=old_weight, new_weight=new_weight, policy=policy, reason=reason,
        )
        self._persist(update)

        log_event(
            logger, component="learning", module="learning.weighting", operation="recompute_weight",
            status=STATUS_SUCCESS, engine_name=engine_name, engine_version=engine_version,
            old_weight=old_weight, new_weight=new_weight, policy=policy.value,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return update

    def _current_weight(self, engine_name: str) -> float:
        record = self.feature_store.get_latest_feature(engine_name, self.config.accuracy_feature_name)
        return record.value if record is not None else self._decision_engine_config.default_accuracy_weight

    def _clamp(self, value: float) -> float:
        return max(self.config.min_weight, min(self.config.max_weight, value))

    def _raw_target(self, accuracy: float) -> float:
        return self._clamp(accuracy / self.config.baseline_accuracy)

    def _exponential_decay_target(
        self, evaluated: List[EngineOutcomeRecord], old_weight: float,
    ) -> Tuple[float, str]:
        accuracy = sum(1 for o in evaluated if o.correct) / len(evaluated)
        raw_target = self._raw_target(accuracy)
        smoothing_factor = self.config.exponential_smoothing_factor
        smoothed = old_weight + smoothing_factor * (raw_target - old_weight)
        reason = (
            f"exponential_decay: accuracy={accuracy:.3f} over {len(evaluated)} samples -> "
            f"raw target {raw_target:.3f}, smoothing_factor={smoothing_factor}"
        )
        return smoothed, reason

    def _rolling_average_target(self, evaluated: List[EngineOutcomeRecord]) -> Tuple[float, str]:
        accuracy = sum(1 for o in evaluated if o.correct) / len(evaluated)
        raw_target = self._raw_target(accuracy)
        reason = f"rolling_average: accuracy={accuracy:.3f} over {len(evaluated)} samples -> target {raw_target:.3f}"
        return raw_target, reason

    def _bayesian_target(self, evaluated: List[EngineOutcomeRecord]) -> Tuple[float, str]:
        n = len(evaluated)
        correct_count = sum(1 for o in evaluated if o.correct)
        prior_mean = self.config.baseline_accuracy
        prior_strength = self.config.bayesian_prior_strength
        prior_alpha = prior_strength * prior_mean
        prior_beta = prior_strength * (1 - prior_mean)
        posterior_alpha = prior_alpha + correct_count
        posterior_beta = prior_beta + (n - correct_count)
        posterior_mean = posterior_alpha / (posterior_alpha + posterior_beta)
        raw_target = self._raw_target(posterior_mean)
        reason = (
            f"bayesian: posterior_mean={posterior_mean:.3f} "
            f"(prior_strength={prior_strength}, prior_mean={prior_mean}) over {n} samples -> "
            f"target {raw_target:.3f}"
        )
        return raw_target, reason

    def _apply_step_cap(self, old_weight: float, target: float) -> float:
        delta = target - old_weight
        capped_delta = max(-self.config.max_weight_step, min(self.config.max_weight_step, delta))
        return self._clamp(old_weight + capped_delta)

    def _persist(self, update: WeightUpdate) -> None:
        self.feature_store.write_feature(
            FeatureValue(symbol=update.engine_name, feature_name=self.config.accuracy_feature_name, value=update.new_weight)
        )
        self.repository.save_weight_update(update)
