"""
Signal data models for the OptiTrade Financial Intelligence Layer.

Signal
------
A single indicator firing with full context: what fired, how strongly,
how confident we are, and why.  The `normalized_value` places the signal
on a universal 0.0-1.0 scale so different indicator families can be compared.

EngineResult
------------
The output of one signal engine (e.g., TECHNICAL, FUNDAMENTAL).  Contains
a list of Signals plus aggregate statistics for the whole engine.

SignalCollection
----------------
One EngineResult per engine type.  Passed through the analyzer and eventually
fed to the DecisionEngine (future phase).
"""
import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Valid field values — document and validate in tests ──────────────────────

VALID_DIRECTIONS  = frozenset({"BULLISH", "BEARISH", "NEUTRAL"})
VALID_STRENGTHS   = frozenset({"STRONG", "MODERATE", "WEAK"})
VALID_TIMEFRAMES  = frozenset({"SHORT", "MEDIUM", "LONG"})
VALID_CATEGORIES  = frozenset({
    "TECHNICAL", "FUNDAMENTAL", "NEWS", "VOLUME", "MARKET_STRUCTURE", "MACRO", "META"
})


@dataclass(frozen=True)
class Signal:
    """
    A single structured indicator signal.

    Fields
    ------
    signal_id        : Unique identifier within an analysis run.  Format: ``{key}_{direction}``.
    indicator        : Human-readable indicator name, e.g. "RSI".
    value            : Raw indicator value (None for pattern/meta signals).
    normalized_value : [0.0, 1.0] — 0=max bearish, 0.5=neutral, 1.0=max bullish.
    direction        : BULLISH | BEARISH | NEUTRAL
    strength         : STRONG (≥70% of max contribution) | MODERATE | WEAK
    confidence       : Per-indicator reliability estimate [0.0, 1.0].
    contribution     : Score delta contributed by this signal.
    reason           : Human-readable explanation (existing Turkish/English text).
    timeframe        : SHORT (intraday/1-3d) | MEDIUM (1-2w) | LONG (weeks-months).
    category         : Which engine family produced this signal.
    """
    signal_id:        str
    indicator:        str
    value:            Optional[float]
    normalized_value: float
    direction:        str
    strength:         str
    confidence:       float
    contribution:     float
    reason:           str
    timeframe:        str
    category:         str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class EngineResult:
    """
    Aggregate output from one signal engine.

    Fields
    ------
    engine          : Engine identifier, e.g. "TECHNICAL".
    signals         : List of individual Signal objects (empty list = no data).
    aggregate_score : Sum of all signal contributions.
    direction       : BULLISH | BEARISH | NEUTRAL — dominant direction by weight.
    confidence      : Weighted-average confidence across directional signals.
    """
    engine:          str
    signals:         List[Signal] = field(default_factory=list)
    aggregate_score: float = 0.0
    direction:       str   = "NEUTRAL"
    confidence:      float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine":          self.engine,
            "aggregate_score": self.aggregate_score,
            "direction":       self.direction,
            "confidence":      self.confidence,
            "signal_count":    len(self.signals),
            "signals":         [s.to_dict() for s in self.signals],
        }

    @classmethod
    def from_signals(cls, engine: str, signals: List[Signal]) -> "EngineResult":
        """
        Build an EngineResult from a list of Signals, computing aggregate
        direction and confidence automatically.

        Direction rule: BULLISH if bull_weight > bear_weight × 1.5, else
        BEARISH or NEUTRAL.  Neutral signals are excluded from weighting.

        Confidence: weighted average of individual confidences, weighted by
        |contribution|.  Directional signals only.
        """
        if not signals:
            return cls(engine=engine, signals=[], aggregate_score=0.0,
                       direction="NEUTRAL", confidence=0.5)

        aggregate = round(sum(s.contribution for s in signals), 2)

        directional = [s for s in signals if s.direction in {"BULLISH", "BEARISH"}]
        bull_w = sum(abs(s.contribution) for s in directional if s.direction == "BULLISH")
        bear_w = sum(abs(s.contribution) for s in directional if s.direction == "BEARISH")

        if bull_w > bear_w * 1.5:
            direction = "BULLISH"
        elif bear_w > bull_w * 1.5:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        total_w = sum(abs(s.contribution) for s in directional)
        confidence = (
            sum(s.confidence * abs(s.contribution) for s in directional) / total_w
            if total_w > 0 else 0.5
        )

        return cls(
            engine          = engine,
            signals         = signals,
            aggregate_score = aggregate,
            direction       = direction,
            confidence      = round(confidence, 3),
        )


@dataclass
class SignalCollection:
    """
    Container for all engine results produced for a single analysis run.

    Engines that have not yet been implemented are None.
    """
    technical:        Optional[EngineResult] = None
    fundamental:      Optional[EngineResult] = None
    news:             Optional[EngineResult] = None
    volume:           Optional[EngineResult] = None
    market_structure: Optional[EngineResult] = None
    macro:            Optional[EngineResult] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for engine_name in (
            "technical", "fundamental", "news",
            "volume", "market_structure", "macro",
        ):
            er: Optional[EngineResult] = getattr(self, engine_name)
            if er is not None:
                result[engine_name] = er.to_dict()
        return result

    @property
    def has_data(self) -> bool:
        return any(
            getattr(self, n) is not None
            for n in ("technical", "fundamental", "news", "volume", "market_structure", "macro")
        )
