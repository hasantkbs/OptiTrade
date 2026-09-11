"""OptiTrade Intelligence Primitives — domain models.

Every model here is derived from an already-final `decision_engine.
models.DecisionOutput` - none of them are produced by voting, scoring,
or an LLM. `RiskBucket` is a shared LOW/MEDIUM/HIGH bucketing of
`DecisionOutput.expected_volatility`, reused by both
`intelligence.decision_diff` and `intelligence.opportunity` so "risk"
means the same thing in both places.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from decision_engine.models import Prediction


class RiskBucket(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ChangeSignificance(str, Enum):
    """How much a `DecisionChange` actually matters. A changed
    `decision` (BUY/HOLD/SELL) is always MATERIAL - everything else is
    judged against `IntelligenceConfig`'s explicit thresholds."""

    NONE = "NONE"
    MINOR = "MINOR"
    MATERIAL = "MATERIAL"


class DecisionChange(BaseModel):
    """The result of comparing one symbol's current `DecisionOutput`
    against its immediately preceding one (if any). Every field is
    derived from the two `DecisionOutput`s themselves - nothing here is
    a new vote or score."""

    symbol: str
    current_decision: Prediction
    previous_decision: Optional[Prediction] = None
    decision_changed: bool

    current_confidence: float
    previous_confidence: Optional[float] = None
    confidence_delta: Optional[float] = None
    confidence_changed_materially: bool = False

    current_expected_return: float
    previous_expected_return: Optional[float] = None
    expected_return_delta: Optional[float] = None
    expected_return_changed_materially: bool = False

    current_risk_bucket: RiskBucket
    previous_risk_bucket: Optional[RiskBucket] = None
    risk_changed: bool = False

    current_data_sufficiency: float
    previous_data_sufficiency: Optional[float] = None
    data_sufficiency_delta: Optional[float] = None
    data_sufficiency_changed_materially: bool = False

    evidence_changed: bool = False

    significance: ChangeSignificance

    current_timestamp: datetime
    previous_timestamp: Optional[datetime] = None


class OpportunityLabel(str, Enum):
    STRONG_BUY_BIAS = "STRONG_BUY_BIAS"
    BUY_BIAS = "BUY_BIAS"
    HOLD = "HOLD"
    WATCH = "WATCH"
    RISK_DETERIORATING = "RISK_DETERIORATING"


class OpportunityAssessment(BaseModel):
    """A product-facing classification of an already-final
    `DecisionOutput` - never a new trading decision. `decision` (the
    real, canonical BUY/HOLD/SELL) is always included so the
    underlying Decision Engine output remains visible and traceable
    behind the product label."""

    symbol: str
    decision: Prediction
    confidence: float
    expected_return: float
    expected_volatility: float
    risk_bucket: RiskBucket
    data_sufficiency: float
    evidence: List[str] = Field(default_factory=list)

    classification: OpportunityLabel
    reason_codes: List[str] = Field(default_factory=list)

    timestamp: datetime
