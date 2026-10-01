"""
OptiTrade Research Lab — promotion recommendation service.

Reuses `learning.service.LearningService.get_accuracy` directly rather
than re-deriving accuracy comparisons. Produces a `PromotionDecision`
recommendation only - PROMOTE / KEEP_SHADOW / REJECT. Nothing in this
package ever writes to `engine_registry` or otherwise actually promotes
a candidate version; a human (or an explicitly separate, later
automation step) must act on the recommendation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from learning.models import RollingWindow
from learning.service import LearningService
from research_lab.config import ResearchLabConfig
from research_lab.models import PromotionDecision, PromotionRecommendation
from research_lab.promotion.repository import PromotionRepository

logger = logging.getLogger(__name__)


class PromotionService:
    def __init__(
        self,
        learning_service: Optional[LearningService] = None,
        repository: Optional[PromotionRepository] = None,
        config: Optional[ResearchLabConfig] = None,
    ) -> None:
        self.learning_service = learning_service or LearningService()
        self.repository = repository or PromotionRepository()
        self.config = config or ResearchLabConfig.from_env()

    def recommend(
        self, engine_name: str, candidate_version: str, live_version: str,
        window: RollingWindow = RollingWindow.THIRTY_DAY, experiment_id: Optional[int] = None,
    ) -> PromotionDecision:
        candidate_metrics = self.learning_service.get_accuracy(engine_name, candidate_version, window)
        live_metrics = self.learning_service.get_accuracy(engine_name, live_version, window)

        live_accuracy = live_metrics.accuracy if live_metrics is not None else 0.0

        if candidate_metrics is None or candidate_metrics.sample_count < self.config.min_samples_for_promotion_decision:
            sample_count = candidate_metrics.sample_count if candidate_metrics is not None else 0
            recommendation = PromotionRecommendation.KEEP_SHADOW
            candidate_accuracy = candidate_metrics.accuracy if candidate_metrics is not None else 0.0
            rationale = (
                f"candidate has only {sample_count} evaluated samples "
                f"(< {self.config.min_samples_for_promotion_decision} required) - needs more shadow data"
            )
        else:
            candidate_accuracy = candidate_metrics.accuracy
            sample_count = candidate_metrics.sample_count
            if candidate_accuracy >= live_accuracy + self.config.promotion_margin:
                recommendation = PromotionRecommendation.PROMOTE
                rationale = (
                    f"candidate accuracy {candidate_accuracy:.3f} exceeds live accuracy {live_accuracy:.3f} "
                    f"by at least the configured margin ({self.config.promotion_margin})"
                )
            elif candidate_accuracy <= live_accuracy - self.config.reject_margin:
                recommendation = PromotionRecommendation.REJECT
                rationale = (
                    f"candidate accuracy {candidate_accuracy:.3f} is below live accuracy {live_accuracy:.3f} "
                    f"by at least the configured margin ({self.config.reject_margin})"
                )
            else:
                recommendation = PromotionRecommendation.KEEP_SHADOW
                rationale = (
                    f"candidate accuracy {candidate_accuracy:.3f} is not clearly better or worse than "
                    f"live accuracy {live_accuracy:.3f} - keep collecting shadow data"
                )

        decision = PromotionDecision(
            experiment_id=experiment_id, engine_name=engine_name, candidate_version=candidate_version,
            live_version=live_version, recommendation=recommendation, rationale=rationale, window=window,
            candidate_accuracy=candidate_accuracy, live_accuracy=live_accuracy,
            candidate_sample_count=sample_count, decided_at=datetime.now(timezone.utc),
        )
        decision.id = self.repository.save(decision)

        log_event(
            logger, component="research_lab", module="research_lab.promotion.service", operation="recommend",
            status=STATUS_SUCCESS, engine_name=engine_name, candidate_version=candidate_version,
            live_version=live_version, recommendation=recommendation.value,
        )
        return decision
