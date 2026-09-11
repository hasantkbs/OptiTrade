"""
OptiTrade Intelligence Primitives — Watchlist Intelligence.

Answers one question for an EXISTING watchlist: "which of these symbols
deserve attention?" This is decision support, not a second decision
engine, not the background scanner (Phase G), and not alert generation
(Phase H) - it never tells anyone to buy/sell and it never persists
anything. It composes, and never duplicates the logic of:

    watchlist.watchlist_service.WatchlistService  - the symbols
                                                     currently tracked
                                                     in a watchlist
    decision_engine.repository                    - persisted
                                                     DecisionOutput
                                                     history, read-only
    intelligence.decision_diff.diff_decisions      - Phase B's own
                                                     materiality rules
    intelligence.opportunity.classify_opportunity  - Phase B's own
                                                     product-label rules
    intelligence.opportunity_ranking.LABEL_PRIORITY - Phase D's own
                                                     label ordering,
                                                     reused (not
                                                     re-derived) to
                                                     decide "improved"
                                                     vs "deteriorated"

This module is the watchlist-domain twin of
`intelligence.portfolio_intelligence` (Phase E) - same finding
semantics, same reuse of Phase B/D primitives, same per-symbol failure
isolation, same read-only/no-scheduler/no-LLM guarantees. It exists
separately because a watchlist symbol is not a held position: there is
no quantity, no allocation, no portfolio-level concentration concept
here, so `WatchlistFindingType.REVIEW_SYMBOL` (not `REVIEW_POSITION`)
names the rollup, and the per-symbol snapshot needs no
value/allocation/risk_bucket fields.

No LLM is called anywhere in this module. No new decision/voting/risk
engine, no new scoring system, no new database table, and no
background scheduler are introduced - `evaluate_watchlist` is a plain,
synchronous, callable function of data already produced elsewhere.

Watchlist-level ranking (this phase's own Step 6) is deliberately NOT
duplicated here: Phase D's `rank_opportunities`/`LABEL_PRIORITY` already
provide the one canonical ranking algorithm, and every question a
future UI/scanner would ask ("which symbols improved/deteriorated/got
riskier/have insufficient data/didn't change") is already answerable
directly from this module's own output - group `findings` by
`finding_type` and `symbol`, or inspect `symbol_snapshots[i].
opportunity.reason_codes` for `"INSUFFICIENT_DATA"` (already exposed by
Phase B, never re-derived here) - without inventing a second sort
implementation or a composite score.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Protocol, runtime_checkable

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.interfaces import ExecutionRepositoryProtocol
from decision_engine.models import DecisionOutput, Prediction
from intelligence.config import IntelligenceConfig
from intelligence.decision_diff import diff_decisions
from intelligence.models import (
    ChangeSignificance,
    OpportunityAssessment,
    RiskBucket,
    WatchlistFinding,
    WatchlistFindingType,
    WatchlistIntelligenceResult,
    WatchlistSymbolSnapshot,
)
from intelligence.opportunity import classify_opportunity
from intelligence.opportunity_ranking import LABEL_PRIORITY
from watchlist.models import WatchlistItem

logger = logging.getLogger(__name__)

_MODULE = "intelligence.watchlist_intelligence"
_COMPONENT = "intelligence"

# Ordinal comparisons only - reused so "deteriorated"/"increased" mean
# "moved toward the worse end of an already-existing enum", never a new
# score. Mirrors the precedent already set by
# `intelligence.opportunity_ranking._RISK_RANK` (Phase D) and
# `intelligence.portfolio_intelligence` (Phase E).
_DECISION_RANK = {Prediction.SELL: 0, Prediction.HOLD: 1, Prediction.BUY: 2}
_RISK_RANK = {RiskBucket.LOW: 0, RiskBucket.MEDIUM: 1, RiskBucket.HIGH: 2}

# A finding of one of these types is what justifies flagging the whole
# symbol for review - OPPORTUNITY_IMPROVED is good news, not a review
# trigger (mirrors Phase E's REVIEW_POSITION policy exactly).
_REVIEW_TRIGGERING_TYPES = frozenset(
    {
        WatchlistFindingType.DECISION_DETERIORATED,
        WatchlistFindingType.RISK_INCREASED,
        WatchlistFindingType.OPPORTUNITY_DETERIORATED,
        WatchlistFindingType.DATA_QUALITY_REDUCED,
    }
)


@runtime_checkable
class WatchlistItemsProviderProtocol(Protocol):
    """The only `watchlist.watchlist_service.WatchlistService` method
    this module depends on - named structurally so a test fake needs no
    other method of the real service."""

    def list_items(self, watchlist_id: int) -> List[WatchlistItem]: ...


def _symbol_findings(
    watchlist_id: int,
    symbol: str,
    decision_change,
    current_assessment: OpportunityAssessment,
    previous_assessment: Optional[OpportunityAssessment],
    detected_at: datetime,
) -> List[WatchlistFinding]:
    """Pure function: turns one symbol's already-computed `DecisionChange`
    (Phase B) and current/previous `OpportunityAssessment` (Phase B) into
    zero or more `WatchlistFinding`s. Never re-derives significance -
    every decision/risk/data-quality finding simply carries
    `decision_change.significance` (Phase B's own combined materiality
    verdict for that diff) forward. Identical logic to
    `intelligence.portfolio_intelligence._position_findings`, applied to
    the watchlist domain's own finding/enum types."""
    findings: List[WatchlistFinding] = []

    if decision_change.decision_changed and decision_change.previous_decision is not None:
        if _DECISION_RANK[decision_change.current_decision] < _DECISION_RANK[decision_change.previous_decision]:
            findings.append(
                WatchlistFinding(
                    watchlist_id=watchlist_id,
                    symbol=symbol,
                    finding_type=WatchlistFindingType.DECISION_DETERIORATED,
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
                WatchlistFinding(
                    watchlist_id=watchlist_id,
                    symbol=symbol,
                    finding_type=WatchlistFindingType.RISK_INCREASED,
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
            WatchlistFindingType.OPPORTUNITY_IMPROVED if current_priority < previous_priority
            else WatchlistFindingType.OPPORTUNITY_DETERIORATED
        )
        findings.append(
            WatchlistFinding(
                watchlist_id=watchlist_id,
                symbol=symbol,
                finding_type=finding_type,
                # A label-priority transition has no Phase B "significance"
                # of its own - treated as MATERIAL by policy, the same way
                # Phase B treats every decision change as always material
                # and Phase E treats every opportunity-label transition.
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
            WatchlistFinding(
                watchlist_id=watchlist_id,
                symbol=symbol,
                finding_type=WatchlistFindingType.DATA_QUALITY_REDUCED,
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
            WatchlistFinding(
                watchlist_id=watchlist_id,
                symbol=symbol,
                finding_type=WatchlistFindingType.REVIEW_SYMBOL,
                significance=ChangeSignificance.MATERIAL,
                detected_at=detected_at,
            )
        )

    return findings


def _build_summary(
    evaluated_count: int,
    finding_count: int,
    review_count: int,
    improved_count: int,
    deteriorated_count: int,
    risk_increased_count: int,
    data_quality_count: int,
    unavailable_count: int,
) -> str:
    """Deterministic prose built only from counts already computed above
    - never generated text, never an LLM call, and never a claim about
    future returns."""
    parts = [f"{evaluated_count} symbol(s) evaluated"]
    if unavailable_count:
        parts.append(f"{unavailable_count} symbol(s) unavailable (no or failed decision history)")
    parts.append(f"{finding_count} finding(s)")
    if review_count:
        parts.append(f"{review_count} symbol(s) flagged for review")
    if improved_count:
        parts.append(f"{improved_count} symbol(s) improved")
    if deteriorated_count:
        parts.append(f"{deteriorated_count} symbol(s) deteriorated")
    if risk_increased_count:
        parts.append(f"{risk_increased_count} symbol(s) riskier")
    if data_quality_count:
        parts.append(f"{data_quality_count} symbol(s) with reduced data quality")
    return "; ".join(parts) + "."


class WatchlistIntelligenceService:
    """Evaluates one existing watchlist's symbols for material
    decision/risk/opportunity/data-quality changes. Read-only: no
    `save()`/`INSERT` of any kind, no background loop, no LLM call, and
    no alert is ever created here."""

    def __init__(
        self,
        watchlist_service: Optional[WatchlistItemsProviderProtocol] = None,
        execution_repository: Optional[ExecutionRepositoryProtocol] = None,
        config: Optional[IntelligenceConfig] = None,
    ) -> None:
        self.config = config or IntelligenceConfig.from_env()
        if watchlist_service is None:
            from watchlist.watchlist_service import WatchlistService

            watchlist_service = WatchlistService()
        self.watchlist_service = watchlist_service
        if execution_repository is None:
            from decision_engine.repository import PostgresExecutionRepository

            execution_repository = PostgresExecutionRepository()
        self.execution_repository = execution_repository

    def evaluate_watchlist(self, watchlist_id: int) -> WatchlistIntelligenceResult:
        items = self.watchlist_service.list_items(watchlist_id)
        # `watchlist_items` already enforces UNIQUE (watchlist_id, symbol)
        # at the database layer (see watchlist/repository.py) - this
        # dedup is a defensive, order-preserving no-op against that
        # contract, the same convention `MarketScanner.scan` (Phase C)
        # already established for a caller-supplied symbol list.
        symbols = list(dict.fromkeys(item.symbol for item in items))
        detected_at = datetime.now(timezone.utc)

        if not symbols:
            result = WatchlistIntelligenceResult(
                watchlist_id=watchlist_id,
                evaluated_at=detected_at,
                summary=_build_summary(0, 0, 0, 0, 0, 0, 0, 0),
            )
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="evaluate_watchlist", status=STATUS_SUCCESS,
                watchlist_id=watchlist_id, evaluated_count=0,
            )
            return result

        snapshots: List[WatchlistSymbolSnapshot] = []
        findings: List[WatchlistFinding] = []
        unavailable_symbols: List[str] = []

        for symbol in symbols:
            try:
                history: List[DecisionOutput] = self.execution_repository.get_recent(symbol, limit=2)
            except Exception as exc:
                self._log_symbol_error(symbol, "get_recent", exc)
                unavailable_symbols.append(symbol)
                snapshots.append(WatchlistSymbolSnapshot(watchlist_id=watchlist_id, symbol=symbol))
                continue

            if not history:
                unavailable_symbols.append(symbol)
                snapshots.append(WatchlistSymbolSnapshot(watchlist_id=watchlist_id, symbol=symbol))
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
                snapshots.append(WatchlistSymbolSnapshot(watchlist_id=watchlist_id, symbol=symbol))
                continue

            snapshots.append(
                WatchlistSymbolSnapshot(
                    watchlist_id=watchlist_id,
                    symbol=symbol,
                    current_decision=current.decision,
                    previous_decision=previous.decision if previous is not None else None,
                    decision_change=decision_change,
                    opportunity=current_assessment,
                )
            )
            findings.extend(
                _symbol_findings(
                    watchlist_id, symbol, decision_change, current_assessment, previous_assessment, detected_at,
                )
            )

        review_symbols = {f.symbol for f in findings if f.finding_type == WatchlistFindingType.REVIEW_SYMBOL}
        improved_symbols = {f.symbol for f in findings if f.finding_type == WatchlistFindingType.OPPORTUNITY_IMPROVED}
        deteriorated_symbols = {
            f.symbol for f in findings
            if f.finding_type in (WatchlistFindingType.DECISION_DETERIORATED, WatchlistFindingType.OPPORTUNITY_DETERIORATED)
        }
        risk_increased_symbols = {f.symbol for f in findings if f.finding_type == WatchlistFindingType.RISK_INCREASED}
        data_quality_symbols = {f.symbol for f in findings if f.finding_type == WatchlistFindingType.DATA_QUALITY_REDUCED}

        result = WatchlistIntelligenceResult(
            watchlist_id=watchlist_id,
            evaluated_at=detected_at,
            evaluated_symbols=symbols,
            symbol_snapshots=snapshots,
            findings=findings,
            unavailable_symbols=unavailable_symbols,
            summary=_build_summary(
                len(symbols), len(findings), len(review_symbols), len(improved_symbols), len(deteriorated_symbols),
                len(risk_increased_symbols), len(data_quality_symbols), len(unavailable_symbols),
            ),
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="evaluate_watchlist", status=STATUS_SUCCESS,
            watchlist_id=watchlist_id, evaluated_count=len(symbols), finding_count=len(findings),
            review_count=len(review_symbols), unavailable_count=len(unavailable_symbols),
        )
        return result

    @staticmethod
    def _log_symbol_error(symbol: str, operation: str, exc: Exception) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_ERROR,
            symbol=symbol, error_type=type(exc).__name__, level=logging.WARNING,
        )
