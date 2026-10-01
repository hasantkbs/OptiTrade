"""
OptiTrade Research Lab — shadow evaluation.

Runs a candidate voting engine's `vote()` directly against a list of
symbols, entirely outside of any live `DecisionEngine.decide()` call,
by delegating straight to
`learning.service.LearningService.record_shadow_vote` - never
duplicating that tracking logic. A shadow pass NEVER affects a live
decision: nothing here is added to any `VotingEngineRegistry` a real
`DecisionEngine` polls.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.interfaces import VotingEngineProtocol
from learning.models import LearningSample, RollingWindow
from learning.service import LearningService

logger = logging.getLogger(__name__)


class ShadowEvaluationService:
    """Thin orchestration layer over `LearningService` for candidate-
    engine evaluation. Holds no persistence of its own - every shadow
    vote is tracked exactly like Continuous Learning already tracks
    one, just tagged `SampleSource.SHADOW`."""

    def __init__(self, learning_service: Optional[LearningService] = None) -> None:
        self.learning_service = learning_service or LearningService()

    def run_shadow_pass(self, engine: VotingEngineProtocol, symbols: List[str]) -> List[LearningSample]:
        samples: List[LearningSample] = []
        for symbol in symbols:
            try:
                samples.append(self.learning_service.record_shadow_vote(engine, symbol))
            except Exception as exc:
                log_event(
                    logger, component="research_lab", module="research_lab.shadow.service",
                    operation="run_shadow_pass", status="error", symbol=symbol,
                    engine_name=getattr(engine, "engine_name", type(engine).__name__),
                    error_type=type(exc).__name__, level=logging.WARNING,
                )
                continue

        log_event(
            logger, component="research_lab", module="research_lab.shadow.service", operation="run_shadow_pass",
            status=STATUS_SUCCESS, engine_name=getattr(engine, "engine_name", type(engine).__name__),
            symbol_count=len(symbols), sample_count=len(samples),
        )
        return samples

    def compare_to_production(self, engine_name: str, shadow_version: str, live_version: str, window: RollingWindow):
        """Read-only comparison against production - never mutates
        anything. Returns `(shadow_accuracy, live_accuracy)`, either of
        which may be `None` if that version has no evaluated samples
        yet for `window`."""
        shadow_metrics = self.learning_service.get_accuracy(engine_name, shadow_version, window)
        live_metrics = self.learning_service.get_accuracy(engine_name, live_version, window)
        return shadow_metrics, live_metrics
