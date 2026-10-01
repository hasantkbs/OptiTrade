"""
OptiTrade Continuous Learning — sample tracker.

The only entry point for turning a completed `DecisionOutput` (live) or
a directly-invoked engine `vote()` (shadow) into a `LearningSample`.
Every sample starts unevaluated - `evaluator.py` fills in the actual
market outcome once `evaluation_horizon_days` has elapsed.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.interfaces import VotingEngineProtocol
from decision_engine.models import DecisionOutput
from learning.config import LearningConfig
from learning.models import LearningSample, SampleSource
from learning.persistence import LearningRepository

logger = logging.getLogger(__name__)


class SampleTracker:
    """Records decisions/shadow votes as learning samples. Never
    predicts, never votes - purely an observer."""

    def __init__(
        self,
        repository: Optional[LearningRepository] = None,
        config: Optional[LearningConfig] = None,
    ) -> None:
        self.repository = repository or LearningRepository()
        self.config = config or LearningConfig.from_env()

    def track_decision(self, output: DecisionOutput) -> LearningSample:
        """Records one live, already-aggregated `DecisionOutput` plus
        every contributing engine's raw vote."""
        sample = LearningSample(
            symbol=output.symbol, source=SampleSource.LIVE, decision=output.decision,
            confidence=output.confidence, expected_return=output.expected_return,
            expected_volatility=output.expected_volatility, engine_results=output.engine_results,
            evidence=output.evidence, decided_at=output.timestamp,
            evaluation_horizon_days=self.config.evaluation_horizon_days,
        )
        sample.id = self.repository.save_sample(sample)
        log_event(
            logger, component="learning", module="learning.tracker", operation="track_decision",
            status=STATUS_SUCCESS, symbol=output.symbol, sample_id=sample.id,
        )
        return sample

    def track_shadow_vote(self, engine: VotingEngineProtocol, symbol: str) -> LearningSample:
        """Directly invokes `engine.vote(symbol)` outside of any live
        `DecisionEngine.decide()` call and records the result as a
        shadow sample - it accumulates accuracy statistics but never
        influences a live decision."""
        vote = engine.vote(symbol)
        sample = LearningSample(
            symbol=symbol, source=SampleSource.SHADOW, decision=vote.prediction,
            confidence=vote.confidence, expected_return=vote.expected_return,
            expected_volatility=vote.volatility, engine_results=[vote], evidence=vote.evidence,
            decided_at=vote.timestamp, evaluation_horizon_days=self.config.evaluation_horizon_days,
        )
        sample.id = self.repository.save_sample(sample)
        log_event(
            logger, component="learning", module="learning.tracker", operation="track_shadow_vote",
            status=STATUS_SUCCESS, symbol=symbol, sample_id=sample.id,
            engine_name=vote.engine_name, engine_version=vote.engine_version,
        )
        return sample
