"""
OptiTrade Intelligence Primitives — Opportunity Classification.

A thin, deterministic, product-facing label over an already-final
`decision_engine.models.DecisionOutput` - never a new BUY/SELL/HOLD
decision, never a new score. `classify_opportunity` only ever reads
fields the Decision Engine already produces (`decision`, `confidence`,
`expected_return`, `expected_volatility`, `data_sufficiency`) and maps
them to one of five fixed product labels via explicit,
`IntelligenceConfig`-driven thresholds - no LLM, no model, no vote.

Rule precedence (first match wins, evaluated top to bottom):

  1. data_sufficiency too low to trust anything stronger -> WATCH
     (conservative default, per this phase's own instruction to prefer
     an honest "not enough information" over inventing a score).
  2. decision == SELL -> RISK_DETERIORATING (the candidate label set
     has no separate "sell bias" label; a genuine sell signal is
     product-framed as "this deserves attention", not silently folded
     into HOLD).
  3. decision == HOLD -> HOLD (direct, unambiguous).
  4. decision == BUY:
       a. confidence below the WATCH threshold -> WATCH (too weak a
          signal to call it a bias).
       b. confidence and data_sufficiency both high, and risk is not
          HIGH -> STRONG_BUY_BIAS.
       c. otherwise -> BUY_BIAS (a BUY signal under elevated volatility
          stays BUY_BIAS, never silently upgraded to STRONG_BUY_BIAS,
          and never miscast as RISK_DETERIORATING - that label is
          reserved for an actual SELL signal from the Decision Engine).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.interfaces import ExecutionRepositoryProtocol
from decision_engine.models import DecisionOutput, Prediction
from intelligence.config import IntelligenceConfig
from intelligence.decision_diff import risk_bucket_for_volatility
from intelligence.exceptions import NoDecisionHistoryError
from intelligence.models import OpportunityAssessment, OpportunityLabel, RiskBucket

logger = logging.getLogger(__name__)

_MODULE = "intelligence.opportunity"
_COMPONENT = "intelligence"


def classify_opportunity(
    decision_output: DecisionOutput,
    config: Optional[IntelligenceConfig] = None,
) -> OpportunityAssessment:
    """Pure, deterministic classification of one `DecisionOutput`."""
    config = config or IntelligenceConfig.from_env()
    risk_bucket = risk_bucket_for_volatility(decision_output.expected_volatility, config)
    reason_codes: List[str] = []

    if decision_output.data_sufficiency < config.min_data_sufficiency_for_classification:
        classification = OpportunityLabel.WATCH
        reason_codes.append("INSUFFICIENT_DATA")
    elif decision_output.decision == Prediction.SELL:
        classification = OpportunityLabel.RISK_DETERIORATING
        reason_codes.append("SELL_SIGNAL")
        if risk_bucket == RiskBucket.HIGH:
            reason_codes.append("HIGH_VOLATILITY")
    elif decision_output.decision == Prediction.HOLD:
        classification = OpportunityLabel.HOLD
        reason_codes.append("HOLD_SIGNAL")
    else:  # Prediction.BUY
        if decision_output.confidence < config.watch_confidence_threshold:
            classification = OpportunityLabel.WATCH
            reason_codes.append("LOW_CONFIDENCE_BUY")
        elif (
            decision_output.confidence >= config.strong_buy_confidence_threshold
            and decision_output.data_sufficiency >= config.strong_buy_min_data_sufficiency
            and risk_bucket != RiskBucket.HIGH
        ):
            classification = OpportunityLabel.STRONG_BUY_BIAS
            reason_codes.append("HIGH_CONFIDENCE_BUY")
            reason_codes.append("SUFFICIENT_DATA")
        else:
            classification = OpportunityLabel.BUY_BIAS
            reason_codes.append("BUY_SIGNAL")
            if risk_bucket == RiskBucket.HIGH:
                reason_codes.append("HIGH_VOLATILITY")

    return OpportunityAssessment(
        symbol=decision_output.symbol,
        decision=decision_output.decision,
        confidence=decision_output.confidence,
        expected_return=decision_output.expected_return,
        expected_volatility=decision_output.expected_volatility,
        risk_bucket=risk_bucket,
        data_sufficiency=decision_output.data_sufficiency,
        evidence=list(decision_output.evidence),
        classification=classification,
        reason_codes=reason_codes,
        timestamp=decision_output.timestamp,
    )


class OpportunityIntelligenceService:
    """Fetches a symbol's most recent `DecisionOutput` from the
    Decision Engine's own execution history and classifies it. Reads
    only - never writes, never persists a duplicate classification."""

    def __init__(
        self,
        repository: Optional[ExecutionRepositoryProtocol] = None,
        config: Optional[IntelligenceConfig] = None,
    ) -> None:
        self.config = config or IntelligenceConfig.from_env()
        if repository is None:
            from decision_engine.repository import PostgresExecutionRepository

            repository = PostgresExecutionRepository()
        self.repository = repository

    def classify_latest(self, symbol: str) -> OpportunityAssessment:
        """Raises `NoDecisionHistoryError` if the symbol has never been
        analyzed."""
        symbol = symbol.upper()
        history = self.repository.get_recent(symbol, limit=1)
        if not history:
            raise NoDecisionHistoryError(symbol)

        assessment = classify_opportunity(history[0], self.config)
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="classify_latest", status=STATUS_SUCCESS,
            symbol=symbol, classification=assessment.classification.value,
        )
        return assessment
