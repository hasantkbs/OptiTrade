"""
OptiTrade Feature Store — feature validation.

Rejects NaN/Inf and out-of-declared-range values before they ever reach
the online or offline stores. Sprint 1 characterized several places where
NaN/Inf silently propagate through existing production code
(`core/risk_manager.py`, `core/ml_predictor.py`) with no error raised;
inside the feature store, a bad value is rejected at the write boundary
instead.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.models import FeatureDefinition, FeatureValue, ValidationResult

logger = logging.getLogger(__name__)


class FeatureValidator:
    """Validates a `FeatureValue` before it is persisted.

    `definitions` is an optional registry of per-feature-name bounds
    (`min_value`/`max_value`); a feature name with no registered
    definition still gets NaN/Inf/type checks, just no range check.
    """

    def __init__(self, definitions: Optional[Dict[str, FeatureDefinition]] = None) -> None:
        self._definitions: Dict[str, FeatureDefinition] = dict(definitions or {})

    def register(self, definition: FeatureDefinition) -> None:
        """Registers (or replaces) the schema/bounds for a feature name."""
        self._definitions[definition.feature_name] = definition

    def validate(self, feature: FeatureValue) -> ValidationResult:
        errors: List[str] = []

        # feature.value is a pydantic-validated `float` field on FeatureValue,
        # so it is already guaranteed numeric by the time it reaches here
        # (pydantic coerces int/bool to float at construction) - only the
        # NaN/Inf/range checks below can actually fail.
        if math.isnan(feature.value):
            errors.append("value is NaN")
        elif math.isinf(feature.value):
            errors.append("value is infinite")
        else:
            definition = self._definitions.get(feature.feature_name)
            if definition is not None:
                if definition.min_value is not None and feature.value < definition.min_value:
                    errors.append(f"value {feature.value} below minimum {definition.min_value}")
                if definition.max_value is not None and feature.value > definition.max_value:
                    errors.append(f"value {feature.value} above maximum {definition.max_value}")

        result = ValidationResult(is_valid=not errors, errors=errors)
        log_event(
            logger,
            component="feature_store",
            module="feature_store.validation",
            operation="validate",
            status=STATUS_SUCCESS if result.is_valid else STATUS_ERROR,
            symbol=feature.symbol,
            feature_name=feature.feature_name,
            error_type="FeatureValidationError" if not result.is_valid else None,
        )
        return result
