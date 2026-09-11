"""
OptiTrade Intelligence Primitives — Decision History Diff.

Compares one symbol's current, already-final `DecisionOutput` against
its immediately preceding one, both read from the Decision Engine's
own persisted history (`decision_engine.repository.
PostgresExecutionRepository`, behind `ExecutionRepositoryProtocol`) -
this module never persists a second copy of decision history and never
computes a new vote, score, or decision. `diff_decisions` is a pure,
deterministic function of two `DecisionOutput`s; `DecisionHistoryDiffService`
is a thin wrapper that fetches those two rows for a symbol.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.interfaces import ExecutionRepositoryProtocol
from decision_engine.models import DecisionOutput
from intelligence.config import IntelligenceConfig
from intelligence.exceptions import NoDecisionHistoryError
from intelligence.models import ChangeSignificance, DecisionChange, RiskBucket

logger = logging.getLogger(__name__)

_MODULE = "intelligence.decision_diff"
_COMPONENT = "intelligence"


def risk_bucket_for_volatility(expected_volatility: float, config: IntelligenceConfig) -> RiskBucket:
    """Same LOW/MEDIUM/HIGH bucketing `pipeline.pipeline.Pipeline.
    _risk_level` applies to a single response's `expected_volatility` -
    reused here (with the same default thresholds) so "risk changed"
    means the same thing as it would in an individual /quant/analyze
    call, not a second, divergent definition of risk."""
    magnitude = abs(expected_volatility)
    if magnitude < config.low_volatility_threshold_pct:
        return RiskBucket.LOW
    if magnitude < config.high_volatility_threshold_pct:
        return RiskBucket.MEDIUM
    return RiskBucket.HIGH


def diff_decisions(
    current: DecisionOutput,
    previous: Optional[DecisionOutput],
    config: Optional[IntelligenceConfig] = None,
) -> DecisionChange:
    """Pure, deterministic comparison of `current` against `previous`
    (the same symbol's immediately preceding decision, or `None` if
    this is the first decision ever recorded for it). Never raises on
    well-formed `DecisionOutput` inputs - callers pass whatever two
    (or one) rows they have; this function makes no assumption about
    which one is chronologically newer beyond the caller's own
    `current`/`previous` labeling, so two rows sharing an identical
    `timestamp` (a real possibility - `get_recent`'s ORDER BY has no
    tie-breaker) are compared exactly as any other pair."""
    config = config or IntelligenceConfig.from_env()
    current_risk_bucket = risk_bucket_for_volatility(current.expected_volatility, config)

    if previous is None:
        return DecisionChange(
            symbol=current.symbol,
            current_decision=current.decision,
            previous_decision=None,
            decision_changed=False,
            current_confidence=current.confidence,
            current_expected_return=current.expected_return,
            current_risk_bucket=current_risk_bucket,
            current_data_sufficiency=current.data_sufficiency,
            evidence_changed=False,
            significance=ChangeSignificance.NONE,
            current_timestamp=current.timestamp,
        )

    previous_risk_bucket = risk_bucket_for_volatility(previous.expected_volatility, config)

    decision_changed = current.decision != previous.decision

    confidence_delta = current.confidence - previous.confidence
    confidence_changed_materially = abs(confidence_delta) >= config.material_confidence_delta

    expected_return_delta = current.expected_return - previous.expected_return
    expected_return_changed_materially = abs(expected_return_delta) >= config.material_expected_return_delta_pct

    risk_changed = current_risk_bucket != previous_risk_bucket

    data_sufficiency_delta = current.data_sufficiency - previous.data_sufficiency
    data_sufficiency_changed_materially = abs(data_sufficiency_delta) >= config.material_data_sufficiency_delta

    evidence_changed = set(current.evidence) != set(previous.evidence)

    if decision_changed or confidence_changed_materially or expected_return_changed_materially or risk_changed:
        significance = ChangeSignificance.MATERIAL
    elif evidence_changed or data_sufficiency_changed_materially:
        significance = ChangeSignificance.MINOR
    else:
        significance = ChangeSignificance.NONE

    return DecisionChange(
        symbol=current.symbol,
        current_decision=current.decision,
        previous_decision=previous.decision,
        decision_changed=decision_changed,
        current_confidence=current.confidence,
        previous_confidence=previous.confidence,
        confidence_delta=confidence_delta,
        confidence_changed_materially=confidence_changed_materially,
        current_expected_return=current.expected_return,
        previous_expected_return=previous.expected_return,
        expected_return_delta=expected_return_delta,
        expected_return_changed_materially=expected_return_changed_materially,
        current_risk_bucket=current_risk_bucket,
        previous_risk_bucket=previous_risk_bucket,
        risk_changed=risk_changed,
        current_data_sufficiency=current.data_sufficiency,
        previous_data_sufficiency=previous.data_sufficiency,
        data_sufficiency_delta=data_sufficiency_delta,
        data_sufficiency_changed_materially=data_sufficiency_changed_materially,
        evidence_changed=evidence_changed,
        significance=significance,
        current_timestamp=current.timestamp,
        previous_timestamp=previous.timestamp,
    )


class DecisionHistoryDiffService:
    """Fetches a symbol's two most recent `DecisionOutput` rows from
    the Decision Engine's own execution history and diffs them. Reads
    only - never writes, never duplicates `decision_engine_executions`."""

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

    def get_latest_change(self, symbol: str) -> DecisionChange:
        """Raises `NoDecisionHistoryError` if the symbol has never been
        analyzed (no rows at all) - there is no "current" decision to
        report a change for in that case. A symbol with exactly one
        recorded decision is not an error: it is diffed against
        `previous=None` (see `diff_decisions`)."""
        symbol = symbol.upper()
        history = self.repository.get_recent(symbol, limit=2)
        if not history:
            raise NoDecisionHistoryError(symbol)

        current = history[0]
        previous = history[1] if len(history) > 1 else None
        change = diff_decisions(current, previous, self.config)

        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="get_latest_change", status=STATUS_SUCCESS,
            symbol=symbol, decision_changed=change.decision_changed, significance=change.significance.value,
        )
        return change
