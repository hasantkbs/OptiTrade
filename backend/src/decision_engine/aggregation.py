"""
OptiTrade Decision Engine — accuracy-weighted vote aggregation.

Pure functions, no I/O — takes already-validated votes plus their
accuracy weights and produces the final decision, confidence, expected
return, and volatility. Kept separate from `service.py` so the
aggregation math itself is directly, deterministically unit-testable
without needing a Feature Store or execution repository.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from decision_engine.models import EngineVote, Prediction


@dataclass
class AggregationResult:
    decision: Prediction
    confidence: float
    expected_return: float
    expected_volatility: float
    evidence: List[str] = field(default_factory=list)


def _effective_weight(vote: EngineVote, accuracy_weight: float) -> float:
    """An engine's influence on the aggregate is its historical accuracy
    weight scaled by how confident it is in this specific vote — an
    accurate engine that is itself unsure contributes less than one that
    is both accurate and confident."""
    return accuracy_weight * vote.confidence


def aggregate_votes(
    votes: List[EngineVote], accuracy_weights: Dict[str, float]
) -> AggregationResult:
    """Aggregates validated votes into a single decision.

    With zero votes, returns a neutral HOLD with zero confidence — the
    caller (DecisionEngine.decide) is responsible for combining this with
    `data_sufficiency` in the final DecisionOutput.
    """
    if not votes:
        return AggregationResult(
            decision=Prediction.HOLD, confidence=0.0,
            expected_return=0.0, expected_volatility=0.0, evidence=[],
        )

    category_weight: Dict[Prediction, float] = {
        Prediction.BUY: 0.0, Prediction.HOLD: 0.0, Prediction.SELL: 0.0,
    }
    total_weight = 0.0
    weighted_return_sum = 0.0
    weighted_volatility_sum = 0.0
    evidence: List[str] = []

    for vote in votes:
        weight = _effective_weight(vote, accuracy_weights.get(vote.engine_name, 1.0))
        category_weight[vote.prediction] += weight
        total_weight += weight
        weighted_return_sum += weight * vote.expected_return
        weighted_volatility_sum += weight * vote.volatility
        evidence.extend(f"{vote.engine_name}: {item}" for item in vote.evidence)

    decision = _resolve_decision(category_weight)

    if total_weight > 0:
        confidence = category_weight[decision] / total_weight
        expected_return = weighted_return_sum / total_weight
        expected_volatility = weighted_volatility_sum / total_weight
    else:
        # Every vote had zero effective weight (e.g. all confidences were
        # 0.0, or all accuracy weights were 0.0) - no basis to prefer any
        # category or average anything.
        confidence = 0.0
        expected_return = 0.0
        expected_volatility = 0.0

    return AggregationResult(
        decision=decision,
        confidence=confidence,
        expected_return=expected_return,
        expected_volatility=expected_volatility,
        evidence=evidence,
    )


def _resolve_decision(category_weight: Dict[Prediction, float]) -> Prediction:
    buy_w = category_weight[Prediction.BUY]
    hold_w = category_weight[Prediction.HOLD]
    sell_w = category_weight[Prediction.SELL]

    if buy_w == 0.0 and sell_w == 0.0 and hold_w == 0.0:
        return Prediction.HOLD

    top = max(buy_w, hold_w, sell_w)
    winners = {pred for pred, w in category_weight.items() if w == top}

    if len(winners) == 1:
        return next(iter(winners))
    # A tie among the top category (most commonly BUY vs SELL) resolves
    # to HOLD - a conservative default rather than an arbitrary pick
    # between two conflicting directional signals.
    return Prediction.HOLD
