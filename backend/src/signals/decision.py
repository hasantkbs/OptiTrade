"""
Decision Engine — Interface Definition
========================================
Defines the contract that future Decision Engine implementations must satisfy.
No aggregation logic is implemented here.

Architecture
------------
The Decision Engine sits above all signal engines:

    TechnicalSignalEngine  ─┐
    FundamentalSignalEngine ─┤
    NewsSignalEngine        ─┤──► DecisionEngine ──► DecisionOutput
    VolumeSignalEngine      ─┤         (Phase C)
    MarketStructureEngine   ─┤
    MacroSignalEngine       ─┘

It receives a SignalCollection (one EngineResult per engine family) and the
current raw score, then produces buy/sell/hold probabilities, confidence,
risk level, and an expected horizon.

Phase C will implement the concrete DecisionEngine.
Until then, NullDecisionEngine can be used as a safe placeholder in tests
and integration checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

from signals.models import SignalCollection


# ── Input / Output DTOs ───────────────────────────────────────────────────────

@dataclass
class DecisionInput:
    """
    Everything the Decision Engine needs to produce a recommendation.

    Fields
    ------
    symbol           : Ticker being analysed.
    asset_type       : "stock" | "crypto"
    signal_collection: Populated SignalCollection from all available engines.
    current_score    : Raw technical score (output of core.scoring.compute_score).
    current_price    : Latest market price (for risk / horizon context).
    """
    symbol:            str
    asset_type:        str
    signal_collection: SignalCollection
    current_score:     float
    current_price:     Optional[float] = None


@dataclass
class DecisionOutput:
    """
    Recommendation produced by the Decision Engine.

    Probabilities
    -------------
    buy_probability, sell_probability, hold_probability each ∈ [0.0, 1.0].
    They should sum to 1.0.

    Fields
    ------
    buy_probability      : Estimated probability that buying is the optimal action.
    sell_probability     : Estimated probability that selling is the optimal action.
    hold_probability     : Estimated probability that holding is the optimal action.
    confidence           : Overall confidence in the recommendation [0.0, 1.0].
    risk_level           : LOW | MEDIUM | HIGH | VERY_HIGH | UNKNOWN
    expected_horizon     : SHORT | MEDIUM | LONG | UNKNOWN
    dominant_direction   : BULLISH | BEARISH | NEUTRAL
    reasoning            : Ordered list of human-readable explanation strings.
    contributing_engines : Engine names that had data and influenced the output.
    """
    buy_probability:      float
    sell_probability:     float
    hold_probability:     float
    confidence:           float
    risk_level:           str
    expected_horizon:     str
    dominant_direction:   str
    reasoning:            List[str]      = field(default_factory=list)
    contributing_engines: List[str]      = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "buy_probability":      self.buy_probability,
            "sell_probability":     self.sell_probability,
            "hold_probability":     self.hold_probability,
            "confidence":           self.confidence,
            "risk_level":           self.risk_level,
            "expected_horizon":     self.expected_horizon,
            "dominant_direction":   self.dominant_direction,
            "reasoning":            self.reasoning,
            "contributing_engines": self.contributing_engines,
        }


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class DecisionEngineProtocol(Protocol):
    """
    Interface every Decision Engine implementation must satisfy.

    Implementations must be stateless with respect to individual analyses —
    all state lives in DecisionInput.  Caching is the caller's responsibility.
    """

    def decide(self, input: DecisionInput) -> DecisionOutput:
        """
        Aggregate signals from all engines and return a recommendation.

        Must never raise; return a low-confidence NEUTRAL output on any
        internal error.
        """
        ...


# ── Null implementation (placeholder) ─────────────────────────────────────────

class NullDecisionEngine:
    """
    A no-op Decision Engine that satisfies DecisionEngineProtocol.

    Returns a neutral, zero-confidence result.  Used as a safe default
    until Phase C implements real aggregation logic.
    """

    def decide(self, input: DecisionInput) -> DecisionOutput:
        engines = [
            name for name in (
                "technical", "fundamental", "news",
                "volume", "market_structure", "macro",
            )
            if getattr(input.signal_collection, name, None) is not None
        ]
        return DecisionOutput(
            buy_probability      = 0.0,
            sell_probability     = 0.0,
            hold_probability     = 1.0,
            confidence           = 0.0,
            risk_level           = "UNKNOWN",
            expected_horizon     = "UNKNOWN",
            dominant_direction   = "NEUTRAL",
            reasoning            = ["Decision Engine not yet implemented (Phase C pending)."],
            contributing_engines = engines,
        )
