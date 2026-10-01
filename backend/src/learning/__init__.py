"""
OptiTrade Continuous Learning.

Observes completed decisions and shadow-engine votes, later compares
them against actual market outcomes, and derives accuracy/calibration/
drift/weighting signals from that history. Writes each engine's
accuracy weight to the Feature Store, which
`decision_engine.weighting.AccuracyWeightProvider` already reads.

Deliberately does NOT self-register into
`engine_registry.registry.default_registry` on import - unlike the
Technical/Fundamental/News engines, this package implements no
`VotingEngineProtocol` and must never participate in live voting.
"""
from learning.models import (
    AccuracyMetrics,
    DriftSignal,
    DriftType,
    EngineOutcomeRecord,
    LearningSample,
    PromotionCandidate,
    RollingWindow,
    SampleSource,
    WeightingPolicy,
    WeightUpdate,
)
from learning.service import LearningService

__all__ = [
    "LearningService",
    "LearningSample",
    "EngineOutcomeRecord",
    "AccuracyMetrics",
    "WeightUpdate",
    "DriftSignal",
    "PromotionCandidate",
    "RollingWindow",
    "WeightingPolicy",
    "DriftType",
    "SampleSource",
]
