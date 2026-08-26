"""
OptiTrade ML Training Platform — model registry promotion lifecycle.

    candidate -> shadow -> active -> archived
         \\--------------> archived
                shadow --> archived

Mirrors `research_lab.experiments.lifecycle`'s "small transition graph +
validator function" shape. No transition is reachable from `archived` -
once archived, a model version is permanently retired; a genuinely
improved model is registered as a brand new `model_id` instead of ever
reviving an old one.
"""
from __future__ import annotations

from typing import Dict, Set

from ml_training.exceptions import InvalidPromotionError
from ml_training.models import PromotionState

VALID_TRANSITIONS: Dict[PromotionState, Set[PromotionState]] = {
    PromotionState.CANDIDATE: {PromotionState.SHADOW, PromotionState.ARCHIVED},
    PromotionState.SHADOW: {PromotionState.ACTIVE, PromotionState.ARCHIVED},
    PromotionState.ACTIVE: {PromotionState.ARCHIVED},
    PromotionState.ARCHIVED: set(),
}


def validate_transition(current: PromotionState, target: PromotionState) -> None:
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidPromotionError(
            f"cannot transition a model from promotion state {current.value!r} to {target.value!r}"
        )
