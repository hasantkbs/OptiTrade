"""OptiTrade Research Lab — benchmarking service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from learning.config import LearningConfig
from learning.models import RollingWindow, WeightingPolicy
from learning.persistence import LearningRepository
from research_lab.benchmarking import comparator, policy_simulation
from research_lab.benchmarking.repository import BenchmarkRepository
from research_lab.config import ResearchLabConfig
from research_lab.models import BenchmarkResult, BenchmarkSubjectType

logger = logging.getLogger(__name__)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


class BenchmarkService:
    """Compares engine versions, weighting policies, and (given
    caller-supplied return series) feature sets/models. Sources engine
    version history straight from Continuous Learning's evaluated
    outcomes - never re-executes any engine."""

    def __init__(
        self,
        learning_repository: Optional[LearningRepository] = None,
        repository: Optional[BenchmarkRepository] = None,
        learning_config: Optional[LearningConfig] = None,
        config: Optional[ResearchLabConfig] = None,
    ) -> None:
        self.learning_repository = learning_repository or LearningRepository()
        self.repository = repository or BenchmarkRepository()
        self.learning_config = learning_config or LearningConfig.from_env()
        self.config = config or ResearchLabConfig.from_env()

    def compare_engine_versions(
        self, engine_name: str, version_a: str, version_b: str, window: RollingWindow, since: Optional[datetime] = None,
    ) -> BenchmarkResult:
        since = since or _EPOCH
        returns_a = self._evaluated_returns(engine_name, version_a, since)
        returns_b = self._evaluated_returns(engine_name, version_b, since)

        result = comparator.compare(
            BenchmarkSubjectType.ENGINE_VERSION, version_a, version_b, returns_a, returns_b, window, self.config,
        )
        result.id = self.repository.save(result)
        log_event(
            logger, component="research_lab", module="research_lab.benchmarking.service",
            operation="compare_engine_versions", status=STATUS_SUCCESS, engine_name=engine_name,
            version_a=version_a, version_b=version_b, significant=result.significant,
        )
        return result

    def compare_weighting_policies(
        self, engine_name: str, engine_version: str, policy_a: WeightingPolicy, policy_b: WeightingPolicy,
        window: RollingWindow = RollingWindow.LIFETIME, since: Optional[datetime] = None, old_weight: float = 1.0,
    ) -> BenchmarkResult:
        since = since or _EPOCH
        outcomes = self.learning_repository.get_engine_outcomes(engine_name, engine_version, since=since)
        evaluated_returns = [o.actual_return for o in outcomes if o.evaluated and o.actual_return is not None]

        target_a, _reason_a = policy_simulation.simulate_policy_target(policy_a, outcomes, old_weight, self.learning_config)
        target_b, _reason_b = policy_simulation.simulate_policy_target(policy_b, outcomes, old_weight, self.learning_config)

        weighted_a = [value * target_a for value in evaluated_returns]
        weighted_b = [value * target_b for value in evaluated_returns]

        result = comparator.compare(
            BenchmarkSubjectType.WEIGHTING_POLICY, policy_a.value, policy_b.value, weighted_a, weighted_b,
            window, self.config,
        )
        result.metrics_a["target_weight"] = target_a
        result.metrics_b["target_weight"] = target_b
        result.id = self.repository.save(result)

        log_event(
            logger, component="research_lab", module="research_lab.benchmarking.service",
            operation="compare_weighting_policies", status=STATUS_SUCCESS, engine_name=engine_name,
            policy_a=policy_a.value, policy_b=policy_b.value,
        )
        return result

    def compare_feature_sets(
        self, name_a: str, returns_a: List[float], name_b: str, returns_b: List[float], window: RollingWindow,
    ) -> BenchmarkResult:
        result = comparator.compare(BenchmarkSubjectType.FEATURE_SET, name_a, name_b, returns_a, returns_b, window, self.config)
        result.id = self.repository.save(result)
        return result

    def compare_models(
        self, name_a: str, returns_a: List[float], name_b: str, returns_b: List[float], window: RollingWindow,
    ) -> BenchmarkResult:
        result = comparator.compare(BenchmarkSubjectType.MODEL, name_a, name_b, returns_a, returns_b, window, self.config)
        result.id = self.repository.save(result)
        return result

    def _evaluated_returns(self, engine_name: str, engine_version: str, since: datetime) -> List[float]:
        outcomes = self.learning_repository.get_engine_outcomes(engine_name, engine_version, since=since)
        return [o.actual_return for o in outcomes if o.evaluated and o.actual_return is not None]
