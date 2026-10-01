"""
OptiTrade Intelligence Primitives — Portfolio Intelligence.

Answers one question for an EXISTING portfolio: "Has anything important
changed in the user's positions that deserves review?" This is decision
support, not a second decision engine - it never tells anyone to
buy/sell. It composes, and never duplicates the logic of:

    portfolio.service.PortfolioService        - open positions (already
                                                 replayed from the
                                                 transaction ledger)
    decision_engine.repository                - persisted DecisionOutput
                                                 history, read-only
    intelligence.decision_diff.diff_decisions  - Phase B's own
                                                 materiality rules
    intelligence.opportunity.classify_opportunity - Phase B's own
                                                 product-label rules
    intelligence.opportunity_ranking.LABEL_PRIORITY - Phase D's own
                                                 label ordering, reused
                                                 (not re-derived) to
                                                 decide "improved" vs
                                                 "deteriorated"

No LLM is called anywhere in this module. No new decision/voting/risk
engine, no new scoring system, no new database table, and no
background scheduler are introduced - `evaluate_portfolio` is a plain,
synchronous, callable function of data already produced elsewhere.

Transaction state vs. market intelligence stay conceptually separate:
a position's `quantity` (from the ledger) never influences whether a
decision/risk/opportunity finding fires - those are derived purely from
Decision Engine history, exactly as they are for any other symbol. A
newly opened, increased, or decreased position is therefore never, by
construction, mistaken for a deteriorated decision (Phase E's Step 8).
Closed positions (quantity <= 0) are excluded from active intelligence
- `PortfolioService.get_positions` already only returns open positions;
this module defensively re-checks that contract rather than trusting it
silently.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Protocol, runtime_checkable

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.interfaces import ExecutionRepositoryProtocol
from decision_engine.models import DecisionOutput, Prediction
from intelligence.config import IntelligenceConfig, PortfolioIntelligenceConfig
from intelligence.decision_diff import diff_decisions
from intelligence.models import (
    ChangeSignificance,
    OpportunityAssessment,
    PortfolioFinding,
    PortfolioFindingType,
    PortfolioIntelligenceResult,
    PortfolioIntelligenceSnapshot,
    PositionFinding,
    PositionFindingType,
    RiskBucket,
)
from intelligence.opportunity import classify_opportunity
from intelligence.opportunity_ranking import LABEL_PRIORITY
from portfolio.models import Position, PositionAnalytics

logger = logging.getLogger(__name__)

_MODULE = "intelligence.portfolio_intelligence"
_COMPONENT = "intelligence"

# Ordinal comparisons only - reused so "deteriorated"/"increased" mean
# "moved toward the worse end of an already-existing enum", never a new
# score. Mirrors the precedent already set by
# `intelligence.opportunity_ranking._RISK_RANK` (Phase D).
_DECISION_RANK = {Prediction.SELL: 0, Prediction.HOLD: 1, Prediction.BUY: 2}
_RISK_RANK = {RiskBucket.LOW: 0, RiskBucket.MEDIUM: 1, RiskBucket.HIGH: 2}

# A position finding of one of these types is what justifies flagging
# the whole position for review - OPPORTUNITY_IMPROVED is good news, not
# a review trigger (Step 6/Step 10: no finding merely because a position
# exists, and improvement alone is not "review-worthy").
_REVIEW_TRIGGERING_TYPES = frozenset(
    {
        PositionFindingType.DECISION_DETERIORATED,
        PositionFindingType.RISK_INCREASED,
        PositionFindingType.OPPORTUNITY_DETERIORATED,
        PositionFindingType.DATA_QUALITY_REDUCED,
    }
)


@runtime_checkable
class PositionsProviderProtocol(Protocol):
    """The only `portfolio.service.PortfolioService` method this module
    depends on - named structurally so a test fake needs no other
    method of the real service."""

    def get_positions(self, portfolio_id: int) -> List[Position]: ...


def _position_findings(
    portfolio_id: int,
    symbol: str,
    decision_change,
    current_assessment: OpportunityAssessment,
    previous_assessment: Optional[OpportunityAssessment],
    detected_at: datetime,
) -> List[PositionFinding]:
    """Pure function: turns one symbol's already-computed `DecisionChange`
    (Phase B) and current/previous `OpportunityAssessment` (Phase B) into
    zero or more `PositionFinding`s. Never re-derives significance -
    every decision/risk/data-quality finding simply carries
    `decision_change.significance` (Phase B's own combined materiality
    verdict for that diff) forward."""
    findings: List[PositionFinding] = []

    if decision_change.decision_changed and decision_change.previous_decision is not None:
        if _DECISION_RANK[decision_change.current_decision] < _DECISION_RANK[decision_change.previous_decision]:
            findings.append(
                PositionFinding(
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    finding_type=PositionFindingType.DECISION_DETERIORATED,
                    significance=decision_change.significance,
                    previous_state=decision_change.previous_decision.value,
                    current_state=decision_change.current_decision.value,
                    decision_change=decision_change,
                    detected_at=detected_at,
                )
            )

    if decision_change.risk_changed and decision_change.previous_risk_bucket is not None:
        if _RISK_RANK[decision_change.current_risk_bucket] > _RISK_RANK[decision_change.previous_risk_bucket]:
            findings.append(
                PositionFinding(
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    finding_type=PositionFindingType.RISK_INCREASED,
                    significance=decision_change.significance,
                    previous_state=decision_change.previous_risk_bucket.value,
                    current_state=decision_change.current_risk_bucket.value,
                    decision_change=decision_change,
                    detected_at=detected_at,
                )
            )

    if previous_assessment is not None and current_assessment.classification != previous_assessment.classification:
        current_priority = LABEL_PRIORITY[current_assessment.classification]
        previous_priority = LABEL_PRIORITY[previous_assessment.classification]
        finding_type = (
            PositionFindingType.OPPORTUNITY_IMPROVED if current_priority < previous_priority
            else PositionFindingType.OPPORTUNITY_DETERIORATED
        )
        findings.append(
            PositionFinding(
                portfolio_id=portfolio_id,
                symbol=symbol,
                finding_type=finding_type,
                # A label-priority transition has no Phase B "significance"
                # of its own (that concept only exists on DecisionChange) -
                # treated as MATERIAL by policy, the same way Phase B
                # treats every decision change as always material.
                significance=ChangeSignificance.MATERIAL,
                previous_state=previous_assessment.classification.value,
                current_state=current_assessment.classification.value,
                opportunity_assessment=current_assessment,
                detected_at=detected_at,
            )
        )

    if (
        decision_change.data_sufficiency_changed_materially
        and decision_change.data_sufficiency_delta is not None
        and decision_change.data_sufficiency_delta < 0
    ):
        findings.append(
            PositionFinding(
                portfolio_id=portfolio_id,
                symbol=symbol,
                finding_type=PositionFindingType.DATA_QUALITY_REDUCED,
                significance=decision_change.significance,
                previous_state=(
                    f"{decision_change.previous_data_sufficiency:.2f}"
                    if decision_change.previous_data_sufficiency is not None else None
                ),
                current_state=f"{decision_change.current_data_sufficiency:.2f}",
                decision_change=decision_change,
                detected_at=detected_at,
            )
        )

    if any(finding.finding_type in _REVIEW_TRIGGERING_TYPES for finding in findings):
        findings.append(
            PositionFinding(
                portfolio_id=portfolio_id,
                symbol=symbol,
                finding_type=PositionFindingType.REVIEW_POSITION,
                significance=ChangeSignificance.MATERIAL,
                detected_at=detected_at,
            )
        )

    return findings


def _portfolio_findings(
    portfolio_id: int,
    position_analytics: Optional[List[PositionAnalytics]],
    config: PortfolioIntelligenceConfig,
    detected_at: datetime,
) -> List[PortfolioFinding]:
    """No arbitrary threshold is invented here - see
    `PortfolioIntelligenceConfig.large_position_weight_pct`'s docstring.
    Conservative by construction: with no configured threshold (the
    default) or no supplied `position_analytics`, this always returns
    an empty list."""
    if config.large_position_weight_pct is None or not position_analytics:
        return []

    findings: List[PortfolioFinding] = []
    for analytics in position_analytics:
        if analytics.weight_pct > config.large_position_weight_pct:
            findings.append(
                PortfolioFinding(
                    portfolio_id=portfolio_id,
                    finding_type=PortfolioFindingType.CONCENTRATION_THRESHOLD_EXCEEDED,
                    significance=ChangeSignificance.MATERIAL,
                    symbol=analytics.symbol,
                    current_state=f"{analytics.weight_pct:.2f}",
                    detected_at=detected_at,
                )
            )
    return findings


def _build_summary(
    open_position_count: int,
    position_finding_count: int,
    review_count: int,
    portfolio_finding_count: int,
    unavailable_count: int,
) -> str:
    """Deterministic prose built only from counts already computed above
    - never generated text, never an LLM call."""
    parts = [f"{open_position_count} open position(s) evaluated"]
    if unavailable_count:
        parts.append(f"{unavailable_count} symbol(s) skipped (no or failed decision history)")
    parts.append(f"{position_finding_count} position finding(s)")
    if review_count:
        parts.append(f"{review_count} position(s) flagged for review")
    if portfolio_finding_count:
        parts.append(f"{portfolio_finding_count} portfolio-level finding(s)")
    return "; ".join(parts) + "."


class PortfolioIntelligenceService:
    """Evaluates one existing portfolio's open positions for material
    decision/risk/opportunity/data-quality changes. Read-only: no
    `save()`/`INSERT` of any kind, no background loop, no LLM call."""

    def __init__(
        self,
        portfolio_service: Optional[PositionsProviderProtocol] = None,
        execution_repository: Optional[ExecutionRepositoryProtocol] = None,
        config: Optional[IntelligenceConfig] = None,
        portfolio_intelligence_config: Optional[PortfolioIntelligenceConfig] = None,
    ) -> None:
        self.config = config or IntelligenceConfig.from_env()
        self.portfolio_intelligence_config = portfolio_intelligence_config or PortfolioIntelligenceConfig.from_env()
        if portfolio_service is None:
            from portfolio.service import PortfolioService

            portfolio_service = PortfolioService()
        self.portfolio_service = portfolio_service
        if execution_repository is None:
            from decision_engine.repository import PostgresExecutionRepository

            execution_repository = PostgresExecutionRepository()
        self.execution_repository = execution_repository

    def evaluate_portfolio(
        self,
        portfolio_id: int,
        position_analytics: Optional[List[PositionAnalytics]] = None,
    ) -> PortfolioIntelligenceResult:
        """`position_analytics` is optional, already-computed
        `portfolio.analytics.PositionAnalyticsService.analyze_positions`
        output (current_value/weight_pct) - this method never fetches a
        live price itself, so it stays fully offline/deterministic when
        the caller doesn't supply it (position findings simply omit
        `current_value`/`allocation_pct`, and no portfolio-level
        concentration finding can fire without it)."""
        positions = self.portfolio_service.get_positions(portfolio_id)
        analytics_by_symbol = {analytics.symbol: analytics for analytics in (position_analytics or [])}

        snapshots: List[PortfolioIntelligenceSnapshot] = []
        position_findings: List[PositionFinding] = []
        unavailable_symbols: List[str] = []
        detected_at = datetime.now(timezone.utc)

        for position in positions:
            # Mirrors PortfolioService.get_positions' own "quantity > 0"
            # contract - defensively re-checked rather than trusted
            # silently, per Step 12 (closed positions are never active
            # intelligence).
            if position.quantity <= 0.0:
                continue

            symbol = position.symbol
            analytics = analytics_by_symbol.get(symbol)

            try:
                history: List[DecisionOutput] = self.execution_repository.get_recent(symbol, limit=2)
            except Exception as exc:
                self._log_symbol_error(symbol, "get_recent", exc)
                unavailable_symbols.append(symbol)
                snapshots.append(self._bare_snapshot(portfolio_id, position, analytics))
                continue

            if not history:
                unavailable_symbols.append(symbol)
                snapshots.append(self._bare_snapshot(portfolio_id, position, analytics))
                continue

            current = history[0]
            previous = history[1] if len(history) > 1 else None

            try:
                decision_change = diff_decisions(current, previous, self.config)
                current_assessment = classify_opportunity(current, self.config)
                previous_assessment = (
                    classify_opportunity(previous, self.config) if previous is not None else None
                )
            except Exception as exc:
                self._log_symbol_error(symbol, "classify", exc)
                unavailable_symbols.append(symbol)
                snapshots.append(self._bare_snapshot(portfolio_id, position, analytics))
                continue

            snapshots.append(
                PortfolioIntelligenceSnapshot(
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    quantity=position.quantity,
                    current_value=analytics.current_value if analytics else None,
                    allocation_pct=analytics.weight_pct if analytics else None,
                    decision=current.decision,
                    opportunity_assessment=current_assessment,
                    risk_bucket=decision_change.current_risk_bucket,
                )
            )
            position_findings.extend(
                _position_findings(
                    portfolio_id, symbol, decision_change, current_assessment, previous_assessment, detected_at,
                )
            )

        portfolio_findings = _portfolio_findings(
            portfolio_id, position_analytics, self.portfolio_intelligence_config, detected_at,
        )
        review_count = sum(
            1 for finding in position_findings if finding.finding_type == PositionFindingType.REVIEW_POSITION
        )
        open_position_count = len(snapshots)

        result = PortfolioIntelligenceResult(
            portfolio_id=portfolio_id,
            evaluated_at=detected_at,
            position_snapshots=snapshots,
            position_findings=position_findings,
            portfolio_findings=portfolio_findings,
            unavailable_symbols=unavailable_symbols,
            summary=_build_summary(
                open_position_count, len(position_findings), review_count, len(portfolio_findings),
                len(unavailable_symbols),
            ),
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="evaluate_portfolio", status=STATUS_SUCCESS,
            portfolio_id=portfolio_id, open_position_count=open_position_count,
            position_finding_count=len(position_findings), review_count=review_count,
            unavailable_count=len(unavailable_symbols),
        )
        return result

    @staticmethod
    def _bare_snapshot(
        portfolio_id: int, position: Position, analytics: Optional[PositionAnalytics],
    ) -> PortfolioIntelligenceSnapshot:
        return PortfolioIntelligenceSnapshot(
            portfolio_id=portfolio_id,
            symbol=position.symbol,
            quantity=position.quantity,
            current_value=analytics.current_value if analytics else None,
            allocation_pct=analytics.weight_pct if analytics else None,
        )

    @staticmethod
    def _log_symbol_error(symbol: str, operation: str, exc: Exception) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_ERROR,
            symbol=symbol, error_type=type(exc).__name__, level=logging.WARNING,
        )
