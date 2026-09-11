"""
OptiTrade Intelligence Primitives.

Reusable, deterministic building blocks derived from an already-final
`decision_engine.models.DecisionOutput` - never a second decision
engine, never a vote, never an LLM call:

- `decision_diff`: compares a symbol's current and previous
  `DecisionOutput` (both read from the Decision Engine's own persisted
  history) and reports what changed.
- `opportunity`: classifies an already-final `DecisionOutput` into a
  product-facing label (STRONG_BUY_BIAS/BUY_BIAS/HOLD/WATCH/
  RISK_DETERIORATING) via explicit, config-driven rules.
- `anomaly`: the canonical `MarketAnomalyDetector` (moved from
  `core.market_anomaly_detector`, which now re-exports this module for
  backward compatibility).

Nothing in this package votes, scores, overrides a Tier-A decision, or
calls an LLM. `pipeline.PipelineService` + `decision_engine` remain the
only canonical production decision path.
"""
from intelligence.anomaly import MarketAlert, MarketAnomalyDetector
from intelligence.decision_diff import DecisionHistoryDiffService, diff_decisions, risk_bucket_for_volatility
from intelligence.models import (
    ChangeSignificance,
    DecisionChange,
    OpportunityAssessment,
    OpportunityLabel,
    RiskBucket,
)
from intelligence.opportunity import OpportunityIntelligenceService, classify_opportunity

__all__ = [
    "ChangeSignificance",
    "DecisionChange",
    "DecisionHistoryDiffService",
    "MarketAlert",
    "MarketAnomalyDetector",
    "OpportunityAssessment",
    "OpportunityIntelligenceService",
    "OpportunityLabel",
    "RiskBucket",
    "classify_opportunity",
    "diff_decisions",
    "risk_bucket_for_volatility",
]
