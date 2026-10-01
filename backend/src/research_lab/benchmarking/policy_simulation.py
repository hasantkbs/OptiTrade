"""
OptiTrade Research Lab — weighting policy simulation.

Simulates what target weight a `learning.weighting` policy would
produce from a given outcome history, WITHOUT touching the Feature
Store or persisting anything - pure reuse of
`learning.weighting.WeightCalculator`'s already-tested target-
computation formulas (`_exponential_decay_target`/
`_rolling_average_target`/`_bayesian_target`), constructed via
`__new__` to skip `WeightCalculator.__init__`'s real Feature Store/
repository connections entirely, since none of those three methods
touch either.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from learning.config import LearningConfig
from learning.models import EngineOutcomeRecord, WeightingPolicy
from learning.weighting import WeightCalculator


def simulate_policy_target(
    policy: WeightingPolicy,
    outcomes: List[EngineOutcomeRecord],
    old_weight: float,
    learning_config: Optional[LearningConfig] = None,
) -> Tuple[float, str]:
    config = learning_config or LearningConfig()
    calculator = WeightCalculator.__new__(WeightCalculator)
    calculator.config = config

    evaluated = [o for o in outcomes if o.evaluated and o.correct is not None]
    if len(evaluated) < config.min_samples_for_weighting:
        return old_weight, f"insufficient evaluated samples ({len(evaluated)} < {config.min_samples_for_weighting})"

    if policy == WeightingPolicy.EXPONENTIAL_DECAY:
        return calculator._exponential_decay_target(evaluated, old_weight)
    if policy == WeightingPolicy.ROLLING_AVERAGE:
        return calculator._rolling_average_target(evaluated)
    if policy == WeightingPolicy.BAYESIAN:
        return calculator._bayesian_target(evaluated)
    raise ValueError(f"unknown weighting policy: {policy}")
