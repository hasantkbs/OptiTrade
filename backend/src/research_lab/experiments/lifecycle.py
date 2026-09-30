"""
OptiTrade Research Lab — experiment lifecycle graph.

    draft -> running -> completed -> promoted -> archived
                               \\--> rejected  -> archived

An experiment can also be abandoned directly from `draft` or `running`
straight to `archived` without ever reaching a verdict. No transition
ever deletes an experiment - `archived` is simply the final resting
status; every prior status transition remains in `updated_at`/history.
"""
from __future__ import annotations

from typing import Dict, Set

from research_lab.exceptions import InvalidExperimentTransitionError
from research_lab.models import ExperimentStatus

VALID_TRANSITIONS: Dict[ExperimentStatus, Set[ExperimentStatus]] = {
    ExperimentStatus.DRAFT: {ExperimentStatus.RUNNING, ExperimentStatus.ARCHIVED},
    ExperimentStatus.RUNNING: {ExperimentStatus.COMPLETED, ExperimentStatus.ARCHIVED},
    ExperimentStatus.COMPLETED: {ExperimentStatus.PROMOTED, ExperimentStatus.REJECTED, ExperimentStatus.ARCHIVED},
    ExperimentStatus.PROMOTED: {ExperimentStatus.ARCHIVED},
    ExperimentStatus.REJECTED: {ExperimentStatus.ARCHIVED},
    ExperimentStatus.ARCHIVED: set(),
}


def validate_transition(current: ExperimentStatus, target: ExperimentStatus) -> None:
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidExperimentTransitionError(current.value, target.value)
