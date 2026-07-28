"""
OptiTrade ML Training Platform — model registry service.

Every trained model is registered here as CANDIDATE. Moving it to
SHADOW (so Continuous Learning starts observing its votes) or to
ACTIVE (making it the live model behind its `engine_name`) are both
explicit, validated state transitions (`registry/lifecycle.py`) -
ACTIVE specifically requires a non-blank human `approved_by`, matching
requirement 11's "human approval remains mandatory". This service
itself NEVER decides to promote a model; `recommend_promotion` only
surfaces `research_lab.promotion.service.PromotionService`'s
recommendation for a human to act on.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from learning.models import RollingWindow
from ml_training.exceptions import InvalidPromotionError
from ml_training.models import ModelRegistryEntry, PromotionState
from ml_training.registry import lifecycle
from ml_training.registry.repository import ModelRegistryRepository
from research_lab.models import PromotionDecision
from research_lab.promotion.service import PromotionService

logger = logging.getLogger(__name__)


class ModelRegistryService:
    def __init__(
        self,
        repository: Optional[ModelRegistryRepository] = None,
        promotion_service: Optional[PromotionService] = None,
    ) -> None:
        self.repository = repository or ModelRegistryRepository()
        self.promotion_service = promotion_service or PromotionService()

    def register(self, entry: ModelRegistryEntry) -> ModelRegistryEntry:
        """Registers a freshly-trained model. Always starts life as
        CANDIDATE - use `start_shadow`/`promote_to_active`/`archive`
        for every subsequent state change."""
        if entry.promotion_state != PromotionState.CANDIDATE:
            raise InvalidPromotionError(
                f"a model must be registered as {PromotionState.CANDIDATE.value!r}, "
                f"got {entry.promotion_state.value!r}"
            )
        entry.id = self.repository.save(entry)
        log_event(
            logger, component="ml_training", module="ml_training.registry.service", operation="register",
            status=STATUS_SUCCESS, model_id=entry.model_id, algorithm=entry.algorithm.value,
        )
        return entry

    def get(self, model_id: str) -> Optional[ModelRegistryEntry]:
        return self.repository.get(model_id)

    def list_by_state(self, promotion_state: Optional[PromotionState] = None, limit: int = 50) -> List[ModelRegistryEntry]:
        return self.repository.list_by_state(promotion_state, limit)

    def start_shadow(self, model_id: str) -> ModelRegistryEntry:
        """CANDIDATE -> SHADOW. No approval required - shadow mode never
        affects a live decision (see `ml_training.shadow`)."""
        return self._transition(model_id, PromotionState.SHADOW, approved_by=None)

    def promote_to_active(self, model_id: str, approved_by: str) -> ModelRegistryEntry:
        """SHADOW -> ACTIVE. Requires a non-blank human approver -
        never invoked automatically by this platform itself."""
        if not approved_by or not approved_by.strip():
            raise InvalidPromotionError("promoting a model to ACTIVE requires a non-blank approved_by")
        return self._transition(model_id, PromotionState.ACTIVE, approved_by=approved_by)

    def archive(self, model_id: str, approved_by: Optional[str] = None) -> ModelRegistryEntry:
        """CANDIDATE/SHADOW/ACTIVE -> ARCHIVED. Terminal - an archived
        model_id is never revived."""
        return self._transition(model_id, PromotionState.ARCHIVED, approved_by=approved_by)

    def recommend_promotion(
        self, model_id: str, live_model_id: str, window: RollingWindow = RollingWindow.THIRTY_DAY,
    ) -> PromotionDecision:
        """Surfaces a PROMOTE / KEEP_SHADOW / REJECT recommendation for
        a SHADOW model against the currently ACTIVE one for the same
        `engine_name`, by reusing
        `research_lab.promotion.service.PromotionService.recommend`
        directly. A recommendation only - never applies it; call
        `promote_to_active`/`archive` yourself once a human has
        reviewed it."""
        candidate = self.repository.get(model_id)
        if candidate is None:
            raise InvalidPromotionError(f"no registered model with model_id {model_id!r}")
        live = self.repository.get(live_model_id)
        if live is None:
            raise InvalidPromotionError(f"no registered model with model_id {live_model_id!r}")

        return self.promotion_service.recommend(
            engine_name=candidate.engine_name, candidate_version=candidate.engine_version,
            live_version=live.engine_version, window=window,
        )

    def _transition(self, model_id: str, target: PromotionState, approved_by: Optional[str]) -> ModelRegistryEntry:
        entry = self.repository.get(model_id)
        if entry is None:
            raise InvalidPromotionError(f"no registered model with model_id {model_id!r}")

        lifecycle.validate_transition(entry.promotion_state, target)
        promoted_at = datetime.now(timezone.utc) if target == PromotionState.ACTIVE else entry.promoted_at
        self.repository.update_promotion_state(model_id, target, approved_by, promoted_at)

        log_event(
            logger, component="ml_training", module="ml_training.registry.service", operation="transition",
            status=STATUS_SUCCESS, model_id=model_id, from_state=entry.promotion_state.value, to_state=target.value,
        )
        entry.promotion_state = target
        entry.approved_by = approved_by
        entry.promoted_at = promoted_at
        return entry
