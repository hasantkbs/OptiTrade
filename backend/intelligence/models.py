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
from pipeline.models import PipelineResponse


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


# ── Market Scanner (batch canonical-pipeline orchestration) ─────────────


class ScanSymbolStatus(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    FAILED = "failed"


class ScanSymbolResult(BaseModel):
    """One symbol's successful scan outcome. `response` is the exact,
    unmodified `pipeline.models.PipelineResponse` `PipelineService.run()`
    already produces - the canonical result type, never re-derived or
    duplicated field-by-field."""

    symbol: str
    status: ScanSymbolStatus = ScanSymbolStatus.SUCCESS
    response: PipelineResponse
    duration_ms: float = Field(..., ge=0.0)


class ScanSymbolFailure(BaseModel):
    """One symbol's failed scan outcome. Only the exception's type name
    is captured (matching `pipeline.executor.EngineExecutionResult`'s
    and `watchlist.scheduler.AlertCheckOutcome`'s own convention) -
    never the raw exception message, which could carry internal detail
    not meant for a caller of this structured result."""

    symbol: str
    status: ScanSymbolStatus  # TIMEOUT or FAILED
    error_type: str
    duration_ms: float = Field(..., ge=0.0)


class MarketScanResult(BaseModel):
    """The full outcome of one `MarketScanner.scan(symbols)` call.
    `unique_symbols` is deduplicated (case-insensitive) but preserves
    the first-occurrence order of the originally requested list -
    `successful`/`failed` are reported in that same deterministic
    order, not completion order."""

    requested_count: int = Field(..., ge=0)
    unique_symbols: List[str] = Field(default_factory=list)
    unique_count: int = Field(..., ge=0)

    successful: List[ScanSymbolResult] = Field(default_factory=list)
    failed: List[ScanSymbolFailure] = Field(default_factory=list)
    successful_count: int = Field(..., ge=0)
    failed_count: int = Field(..., ge=0)

    started_at: datetime
    completed_at: datetime
    duration_ms: float = Field(..., ge=0.0)


# ── Opportunity Ranking (presentation layer over a MarketScanResult) ────


class RankingReason(BaseModel):
    """The two derived ordering keys not already present on
    `OpportunityAssessment` - `label_priority` (lower = ranked first;
    see `intelligence.opportunity_ranking.LABEL_PRIORITY`) and
    `risk_rank` (lower = lower risk = ranked first). Confidence,
    expected_return, data_sufficiency, and the classification itself
    are already on `RankedOpportunity.assessment` - not duplicated
    here, so comparing two items' `assessment` + `reason` together
    fully explains their relative order without a composite score."""

    label_priority: int = Field(..., ge=0)
    risk_rank: int = Field(..., ge=0)


class RankedOpportunity(BaseModel):
    """One already-analyzed, already-classified symbol's position in a
    ranking. `assessment` (Phase B's classification) and `response`
    (Phase C's canonical `PipelineResponse`) are referenced, not
    copied field-by-field - full traceability back to the real
    Decision Engine output stays one attribute away."""

    rank: int = Field(..., ge=1)
    symbol: str
    assessment: OpportunityAssessment
    response: PipelineResponse
    reason: RankingReason


class OpportunityRankingResult(BaseModel):
    """The full outcome of one `intelligence.opportunity_ranking.
    rank_opportunities(scan_result)` call. `failed_symbols` mirrors the
    scan's own failures (never ranked); `unclassifiable_symbols` is the
    rare defensive case where a successfully-scanned symbol's result
    could not be classified at all - excluded rather than crashing the
    whole ranking."""

    ranked: List[RankedOpportunity] = Field(default_factory=list)
    failed_symbols: List[str] = Field(default_factory=list)
    unclassifiable_symbols: List[str] = Field(default_factory=list)
    ranked_count: int = Field(..., ge=0)
    total_scanned_count: int = Field(..., ge=0)


# ── Portfolio Intelligence (change-detection over an existing portfolio) ─


class PositionFindingType(str, Enum):
    """Product-facing decision-support language (never an instruction to
    buy/sell) for a change detected on one open position."""

    DECISION_DETERIORATED = "DECISION_DETERIORATED"
    RISK_INCREASED = "RISK_INCREASED"
    OPPORTUNITY_IMPROVED = "OPPORTUNITY_IMPROVED"
    OPPORTUNITY_DETERIORATED = "OPPORTUNITY_DETERIORATED"
    DATA_QUALITY_REDUCED = "DATA_QUALITY_REDUCED"
    REVIEW_POSITION = "REVIEW_POSITION"


class PortfolioFindingType(str, Enum):
    """Portfolio-wide (not single-position) findings. Only one exists in
    this phase, and it only ever fires when an operator has explicitly
    configured `PortfolioIntelligenceConfig.large_position_weight_pct` -
    see that field's docstring for why no default threshold is invented."""

    CONCENTRATION_THRESHOLD_EXCEEDED = "CONCENTRATION_THRESHOLD_EXCEEDED"


class PositionFinding(BaseModel):
    """One deterministic, decision-support finding for one symbol.
    `decision_change`/`opportunity_assessment` are referenced (not
    copied field-by-field) so the finding stays traceable back to the
    canonical `DecisionOutput`s behind it without duplicating their
    data. `significance` is always Phase B's own `ChangeSignificance`
    (from `decision_change.significance` where the finding derives from
    a `DecisionChange`) - never a new severity scale."""

    portfolio_id: int
    symbol: str
    finding_type: PositionFindingType
    significance: ChangeSignificance
    previous_state: Optional[str] = None
    current_state: Optional[str] = None
    decision_change: Optional[DecisionChange] = None
    opportunity_assessment: Optional[OpportunityAssessment] = None
    detected_at: datetime


class PortfolioFinding(BaseModel):
    """One portfolio-wide finding - currently only concentration, and
    only when explicitly configured (see `PortfolioFindingType`)."""

    portfolio_id: int
    finding_type: PortfolioFindingType
    significance: ChangeSignificance
    symbol: Optional[str] = None
    previous_state: Optional[str] = None
    current_state: Optional[str] = None
    detected_at: datetime


class PortfolioIntelligenceSnapshot(BaseModel):
    """The minimum per-position state needed to compare a portfolio over
    time - deliberately not the full `portfolio.models.PortfolioDashboard`
    response. `current_value`/`allocation_pct` are populated only when
    the caller supplies already-computed `PositionAnalytics` (this
    module never fetches a live price itself); `decision`/
    `opportunity_assessment`/`risk_bucket` are populated only when the
    symbol has recorded Decision Engine history."""

    portfolio_id: int
    symbol: str
    quantity: float = Field(..., ge=0.0)
    current_value: Optional[float] = None
    allocation_pct: Optional[float] = None
    decision: Optional[Prediction] = None
    opportunity_assessment: Optional[OpportunityAssessment] = None
    risk_bucket: Optional[RiskBucket] = None


class PortfolioIntelligenceResult(BaseModel):
    """The full outcome of one `intelligence.portfolio_intelligence.
    PortfolioIntelligenceService.evaluate_portfolio(portfolio_id)` call.
    `unavailable_symbols` covers both "never analyzed" (no Decision
    Engine history at all) and "lookup failed" (a per-symbol exception,
    isolated the same way `MarketScanner`/`rank_opportunities` isolate a
    single bad symbol) - both are handled conservatively: no finding is
    produced for a symbol that can't be evaluated."""

    portfolio_id: int
    evaluated_at: datetime
    position_snapshots: List[PortfolioIntelligenceSnapshot] = Field(default_factory=list)
    position_findings: List[PositionFinding] = Field(default_factory=list)
    portfolio_findings: List[PortfolioFinding] = Field(default_factory=list)
    unavailable_symbols: List[str] = Field(default_factory=list)
    summary: str
