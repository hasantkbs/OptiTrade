"""
OptiTrade Decision Engine — vote validation.

`EngineVote.confidence` is already range-checked by pydantic (0.0-1.0),
but `expected_return` and `volatility` are plain, unconstrained floats —
a voting engine returning NaN/Inf for either must not be allowed to
silently corrupt the weighted aggregation (see
docs/architecture/migration-notes.md's `ml_predictor.py`/`risk_manager.py`
sections for exactly this failure mode occurring elsewhere in this
codebase). Reuses `feature_store.models.ValidationResult` rather than
defining an equivalent shape a second time.
"""
from __future__ import annotations

import logging
import math
from typing import List

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.models import EngineVote
from feature_store.models import ValidationResult

logger = logging.getLogger(__name__)


def validate_vote(vote: EngineVote) -> ValidationResult:
    errors: List[str] = []

    for field_name in ("expected_return", "volatility"):
        value = getattr(vote, field_name)
        if math.isnan(value):
            errors.append(f"{field_name} is NaN")
        elif math.isinf(value):
            errors.append(f"{field_name} is infinite")

    if vote.volatility < 0:
        errors.append(f"volatility must be non-negative, got {vote.volatility}")

    result = ValidationResult(is_valid=not errors, errors=errors)
    log_event(
        logger,
        component="decision_engine",
        module="decision_engine.validation",
        operation="validate_vote",
        status=STATUS_SUCCESS if result.is_valid else STATUS_ERROR,
        engine_name=vote.engine_name,
        error_type="InvalidVoteError" if not result.is_valid else None,
    )
    return result
