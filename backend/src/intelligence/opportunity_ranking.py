"""
OptiTrade Intelligence Primitives — Opportunity Ranking.

A deterministic presentation layer over an already-produced
`intelligence.models.MarketScanResult` (Phase C's `MarketScanner`) and
`intelligence.opportunity.classify_opportunity` (Phase B) - this module
computes neither a decision nor a score. It only orders symbols that
were already classified, using the classification and the already-
existing fields behind it (confidence, expected_return, risk bucket).

No LLM is called anywhere in this module. No new scoring/voting/risk
engine is introduced - `rank_opportunities` is a pure function of data
already produced elsewhere:

    MarketScanner.scan(symbols)
        -> MarketScanResult
    rank_opportunities(scan_result)
        -> OpportunityRankingResult (uses classify_opportunity internally)

Deliberately NOT a composite numeric "opportunity score": the ordering
is a plain, explicit sort key (label priority, then confidence, then
expected_return as a tie-breaker only, then risk, then symbol) - never
collapsed into one number. `RankedOpportunity.reason` plus
`RankedOpportunity.assessment` together make the ordering fully
explainable without any generated prose.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Protocol, Tuple, runtime_checkable

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.models import DecisionOutput
from intelligence.config import IntelligenceConfig
from intelligence.models import (
    MarketScanResult,
    OpportunityAssessment,
    OpportunityLabel,
    OpportunityRankingResult,
    RankedOpportunity,
    RankingReason,
    RiskBucket,
)
from intelligence.opportunity import classify_opportunity
from pipeline.models import PipelineResponse

logger = logging.getLogger(__name__)

_MODULE = "intelligence.opportunity_ranking"
_COMPONENT = "intelligence"

# Best (ranked first) to worst (ranked last). Explicit and tested
# (test_opportunity_ranking_label_priority.py) rather than relying on
# enum declaration order, which would silently change meaning if
# `OpportunityLabel`'s member order ever changed for an unrelated
# reason. Conservative by construction: RISK_DETERIORATING is always
# last, WATCH/HOLD never outrank a BUY-bias label.
LABEL_PRIORITY = {
    OpportunityLabel.STRONG_BUY_BIAS: 0,
    OpportunityLabel.BUY_BIAS: 1,
    OpportunityLabel.HOLD: 2,
    OpportunityLabel.WATCH: 3,
    OpportunityLabel.RISK_DETERIORATING: 4,
}

# Lower risk ranks first. Reuses the existing RiskBucket enum
# (Phase B) - not a new risk calculation.
_RISK_RANK = {
    RiskBucket.LOW: 0,
    RiskBucket.MEDIUM: 1,
    RiskBucket.HIGH: 2,
}


def _decision_output_from_response(response: PipelineResponse) -> DecisionOutput:
    """Bridges Phase C's `PipelineResponse` to the `DecisionOutput`
    shape `classify_opportunity` (Phase B) expects. Every value is
    copied from the response itself - `data_sufficiency` and
    `timestamp` are simply nested differently on `PipelineResponse`
    (under `.risk`/`.metadata`) than on `DecisionOutput`, nothing is
    invented. `engine_results` is left empty: `classify_opportunity`
    never reads it, and `OpportunityAssessment` has no field for it
    either, so reconstructing per-engine `EngineVote`s from
    `PipelineResponse.engine_breakdown` would add real complexity for
    zero behavioral difference."""
    return DecisionOutput(
        symbol=response.symbol,
        decision=response.decision,
        confidence=response.confidence,
        expected_return=response.expected_return,
        expected_volatility=response.expected_volatility,
        aggregation_strategy_version=response.metadata.pipeline_version,
        data_sufficiency=response.risk.data_sufficiency,
        evidence=response.evidence,
        engine_results=[],
        timestamp=response.metadata.timestamp,
    )


def _sort_key(assessment: OpportunityAssessment) -> Tuple[int, float, float, int, str]:
    """The complete, explicit ordering key - never collapsed into a
    single composite score. Data-sufficiency conservatism is inherited
    entirely from `classify_opportunity` itself (an insufficiently-
    supported BUY is already reclassified to WATCH there) - this key
    adds no separate data-quality check of its own, per Phase B's own
    semantics."""
    return (
        LABEL_PRIORITY[assessment.classification],
        -assessment.confidence,
        -assessment.expected_return,
        _RISK_RANK[assessment.risk_bucket],
        assessment.symbol,
    )


@runtime_checkable
class ScannerProtocol(Protocol):
    """The only contract `scan_and_rank` depends on -
    `intelligence.market_scanner.MarketScanner`'s real shape, defined
    here structurally (not imported) so this module has no dependency
    on `market_scanner` and a test can inject a fake scanner freely."""

    def scan(self, symbols: List[str]) -> MarketScanResult: ...


def rank_opportunities(
    scan_result: MarketScanResult,
    config: Optional[IntelligenceConfig] = None,
) -> OpportunityRankingResult:
    """Classifies and orders every successfully-scanned symbol in
    `scan_result`. Symbols the scan itself already failed for are
    reported separately in `failed_symbols` and never ranked. A symbol
    whose successful scan result cannot be classified for some reason
    (defensive - `classify_opportunity` does not raise for any
    well-formed `PipelineResponse`) is excluded via
    `unclassifiable_symbols` rather than crashing the whole call, the
    same failure-isolation principle `MarketScanner` itself already
    applies at the scan layer."""
    config = config or IntelligenceConfig.from_env()

    candidates: List[Tuple[OpportunityAssessment, PipelineResponse]] = []
    unclassifiable_symbols: List[str] = []

    for scan_symbol_result in scan_result.successful:
        try:
            decision_output = _decision_output_from_response(scan_symbol_result.response)
            assessment = classify_opportunity(decision_output, config)
        except Exception as exc:
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="classify", status=STATUS_ERROR,
                symbol=scan_symbol_result.symbol, error_type=type(exc).__name__, level=logging.WARNING,
            )
            unclassifiable_symbols.append(scan_symbol_result.symbol)
            continue
        candidates.append((assessment, scan_symbol_result.response))

    candidates.sort(key=lambda pair: _sort_key(pair[0]))

    ranked = [
        RankedOpportunity(
            rank=index + 1,
            symbol=assessment.symbol,
            assessment=assessment,
            response=response,
            reason=RankingReason(
                label_priority=LABEL_PRIORITY[assessment.classification],
                risk_rank=_RISK_RANK[assessment.risk_bucket],
            ),
        )
        for index, (assessment, response) in enumerate(candidates)
    ]

    failed_symbols = [failure.symbol for failure in scan_result.failed]

    result = OpportunityRankingResult(
        ranked=ranked,
        failed_symbols=failed_symbols,
        unclassifiable_symbols=unclassifiable_symbols,
        ranked_count=len(ranked),
        total_scanned_count=scan_result.unique_count,
    )
    log_event(
        logger, component=_COMPONENT, module=_MODULE, operation="rank_opportunities", status=STATUS_SUCCESS,
        ranked_count=result.ranked_count, failed_count=len(failed_symbols),
        unclassifiable_count=len(unclassifiable_symbols),
    )
    return result


def scan_and_rank(
    scanner: ScannerProtocol, symbols: List[str], config: Optional[IntelligenceConfig] = None,
) -> OpportunityRankingResult:
    """Convenience composition of Phase C's scanner and this module's
    ranking - `MarketScanner.scan(symbols) -> MarketScanResult ->
    rank_opportunities(...) -> OpportunityRankingResult`."""
    scan_result = scanner.scan(symbols)
    return rank_opportunities(scan_result, config)
