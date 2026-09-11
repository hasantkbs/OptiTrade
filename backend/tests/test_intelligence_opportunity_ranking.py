"""
Tests for intelligence/opportunity_ranking.py.

`rank_opportunities` is a pure function of an already-constructed
`MarketScanResult` - no database, no network, no live `MarketScanner`
or `PipelineService` needed. `scan_and_rank` is tested separately
against a fake satisfying `ScannerProtocol`.
"""
from datetime import datetime, timezone
from typing import List, Optional

import pytest

from decision_engine.models import Prediction
from intelligence.config import IntelligenceConfig
from intelligence.models import (
    MarketScanResult,
    OpportunityLabel,
    RiskBucket,
    ScanSymbolFailure,
    ScanSymbolResult,
    ScanSymbolStatus,
)
from intelligence.opportunity_ranking import LABEL_PRIORITY, rank_opportunities, scan_and_rank
from pipeline.models import PipelineMetadata, PipelineResponse, RiskAssessment

_CONFIG = IntelligenceConfig()
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _response(
    symbol: str,
    decision: Prediction = Prediction.BUY,
    confidence: float = 0.8,
    expected_return: float = 5.0,
    expected_volatility: float = 8.0,  # LOW risk bucket
    data_sufficiency: float = 1.0,
    evidence: Optional[List[str]] = None,
) -> PipelineResponse:
    return PipelineResponse(
        symbol=symbol, decision=decision, confidence=confidence, expected_return=expected_return,
        expected_volatility=expected_volatility,
        risk=RiskAssessment(risk_level="LOW", expected_volatility=expected_volatility, data_sufficiency=data_sufficiency),
        explanation="test explanation",
        evidence=evidence or [],
        metadata=PipelineMetadata(
            pipeline_version="v1", total_duration_ms=1.0, engines_available=3, engines_succeeded=3, degraded=False,
            timestamp=_NOW,
        ),
    )


def _success(symbol: str, **response_overrides) -> ScanSymbolResult:
    return ScanSymbolResult(symbol=symbol, status=ScanSymbolStatus.SUCCESS, response=_response(symbol, **response_overrides), duration_ms=1.0)


def _failure(symbol: str, error_type: str = "ValueError") -> ScanSymbolFailure:
    return ScanSymbolFailure(symbol=symbol, status=ScanSymbolStatus.FAILED, error_type=error_type, duration_ms=1.0)


def _scan_result(successful: Optional[List[ScanSymbolResult]] = None, failed: Optional[List[ScanSymbolFailure]] = None) -> MarketScanResult:
    successful = successful or []
    failed = failed or []
    unique = [s.symbol for s in successful] + [f.symbol for f in failed]
    return MarketScanResult(
        requested_count=len(unique), unique_symbols=unique, unique_count=len(unique),
        successful=successful, failed=failed, successful_count=len(successful), failed_count=len(failed),
        started_at=_NOW, completed_at=_NOW, duration_ms=1.0,
    )


# ── basic shape ────────────────────────────────────────────────────────


def test_empty_scan_produces_empty_ranking():
    result = rank_opportunities(_scan_result())

    assert result.ranked == []
    assert result.failed_symbols == []
    assert result.unclassifiable_symbols == []
    assert result.ranked_count == 0
    assert result.total_scanned_count == 0


def test_single_opportunity():
    scan_result = _scan_result(successful=[_success("AAPL")])
    result = rank_opportunities(scan_result)

    assert result.ranked_count == 1
    assert result.ranked[0].rank == 1
    assert result.ranked[0].symbol == "AAPL"


def test_multiple_opportunities_are_all_ranked():
    scan_result = _scan_result(
        successful=[
            _success("AAPL", confidence=0.9, data_sufficiency=1.0),
            _success("MSFT", decision=Prediction.HOLD),
            _success("NVDA", decision=Prediction.SELL, expected_volatility=40.0),
        ]
    )
    result = rank_opportunities(scan_result)

    assert result.ranked_count == 3
    assert {r.symbol for r in result.ranked} == {"AAPL", "MSFT", "NVDA"}
    assert [r.rank for r in result.ranked] == [1, 2, 3]


# ── label priority ──────────────────────────────────────────────────────


def test_strong_buy_bias_outranks_buy_bias():
    scan_result = _scan_result(
        successful=[
            _success("WEAK", decision=Prediction.BUY, confidence=0.6, data_sufficiency=1.0, expected_volatility=8.0),
            _success("STRONG", decision=Prediction.BUY, confidence=0.9, data_sufficiency=1.0, expected_volatility=8.0),
        ]
    )
    result = rank_opportunities(scan_result)

    assert result.ranked[0].symbol == "STRONG"
    assert result.ranked[0].assessment.classification == OpportunityLabel.STRONG_BUY_BIAS
    assert result.ranked[1].symbol == "WEAK"
    assert result.ranked[1].assessment.classification == OpportunityLabel.BUY_BIAS


def test_buy_bias_outranks_hold():
    scan_result = _scan_result(
        successful=[
            _success("HOLDER", decision=Prediction.HOLD),
            _success("BUYER", decision=Prediction.BUY, confidence=0.6),
        ]
    )
    result = rank_opportunities(scan_result)

    assert result.ranked[0].symbol == "BUYER"
    assert result.ranked[0].assessment.classification == OpportunityLabel.BUY_BIAS
    assert result.ranked[1].symbol == "HOLDER"
    assert result.ranked[1].assessment.classification == OpportunityLabel.HOLD


def test_hold_outranks_watch():
    scan_result = _scan_result(
        successful=[
            _success("WATCHED", decision=Prediction.BUY, confidence=0.4),  # below watch threshold -> WATCH
            _success("HOLDER", decision=Prediction.HOLD),
        ]
    )
    result = rank_opportunities(scan_result)

    assert result.ranked[0].symbol == "HOLDER"
    assert result.ranked[0].assessment.classification == OpportunityLabel.HOLD
    assert result.ranked[1].symbol == "WATCHED"
    assert result.ranked[1].assessment.classification == OpportunityLabel.WATCH


def test_watch_outranks_risk_deteriorating():
    scan_result = _scan_result(
        successful=[
            _success("SELLER", decision=Prediction.SELL),
            _success("WATCHED", decision=Prediction.BUY, confidence=0.4),
        ]
    )
    result = rank_opportunities(scan_result)

    assert result.ranked[0].symbol == "WATCHED"
    assert result.ranked[0].assessment.classification == OpportunityLabel.WATCH
    assert result.ranked[1].symbol == "SELLER"
    assert result.ranked[1].assessment.classification == OpportunityLabel.RISK_DETERIORATING


def test_label_priority_is_conservative_and_covers_every_label():
    assert LABEL_PRIORITY[OpportunityLabel.STRONG_BUY_BIAS] < LABEL_PRIORITY[OpportunityLabel.BUY_BIAS]
    assert LABEL_PRIORITY[OpportunityLabel.BUY_BIAS] < LABEL_PRIORITY[OpportunityLabel.HOLD]
    assert LABEL_PRIORITY[OpportunityLabel.HOLD] < LABEL_PRIORITY[OpportunityLabel.WATCH]
    assert LABEL_PRIORITY[OpportunityLabel.WATCH] < LABEL_PRIORITY[OpportunityLabel.RISK_DETERIORATING]
    assert set(LABEL_PRIORITY.keys()) == set(OpportunityLabel)  # exactly the five existing labels, no sixth


# ── confidence / expected_return / risk tie-breaking ────────────────────


def test_confidence_orders_otherwise_equal_opportunities():
    scan_result = _scan_result(
        successful=[
            _success("LOWER", decision=Prediction.BUY, confidence=0.6, expected_return=5.0, expected_volatility=8.0),
            _success("HIGHER", decision=Prediction.BUY, confidence=0.7, expected_return=5.0, expected_volatility=8.0),
        ]
    )
    result = rank_opportunities(scan_result)

    assert [r.symbol for r in result.ranked] == ["HIGHER", "LOWER"]


def test_expected_return_is_a_tiebreaker_only_after_confidence():
    """A lower-confidence, higher-expected-return opportunity must NOT
    outrank a higher-confidence one - expected_return only breaks ties
    among equal-confidence, same-label opportunities."""
    scan_result = _scan_result(
        successful=[
            _success("HIGH_RETURN_LOW_CONF", decision=Prediction.BUY, confidence=0.56, expected_return=50.0, expected_volatility=8.0),
            _success("LOW_RETURN_HIGH_CONF", decision=Prediction.BUY, confidence=0.7, expected_return=1.0, expected_volatility=8.0),
        ]
    )
    result = rank_opportunities(scan_result)

    assert [r.symbol for r in result.ranked] == ["LOW_RETURN_HIGH_CONF", "HIGH_RETURN_LOW_CONF"]


def test_expected_return_breaks_ties_when_confidence_is_equal():
    scan_result = _scan_result(
        successful=[
            _success("LOWER_RETURN", decision=Prediction.BUY, confidence=0.6, expected_return=2.0, expected_volatility=8.0),
            _success("HIGHER_RETURN", decision=Prediction.BUY, confidence=0.6, expected_return=8.0, expected_volatility=8.0),
        ]
    )
    result = rank_opportunities(scan_result)

    assert [r.symbol for r in result.ranked] == ["HIGHER_RETURN", "LOWER_RETURN"]


def test_risk_orders_otherwise_equal_opportunities():
    scan_result = _scan_result(
        successful=[
            _success("RISKIER", decision=Prediction.BUY, confidence=0.6, expected_return=5.0, expected_volatility=15.0),  # MEDIUM
            _success("SAFER", decision=Prediction.BUY, confidence=0.6, expected_return=5.0, expected_volatility=8.0),  # LOW
        ]
    )
    result = rank_opportunities(scan_result)

    assert [r.symbol for r in result.ranked] == ["SAFER", "RISKIER"]
    assert result.ranked[0].assessment.risk_bucket == RiskBucket.LOW
    assert result.ranked[1].assessment.risk_bucket == RiskBucket.MEDIUM


def test_high_expected_return_does_not_compensate_for_higher_risk_via_a_ratio():
    """There is no return/risk ratio - a same-label, same-confidence
    opportunity with higher expected_return but also higher risk is
    still ordered by expected_return first (the declared hierarchy),
    never by some derived reward-per-unit-risk score."""
    scan_result = _scan_result(
        successful=[
            _success("HIGH_RETURN_HIGH_RISK", decision=Prediction.BUY, confidence=0.6, expected_return=20.0, expected_volatility=40.0),  # HIGH risk
            _success("LOW_RETURN_LOW_RISK", decision=Prediction.BUY, confidence=0.6, expected_return=5.0, expected_volatility=8.0),  # LOW risk
        ]
    )
    result = rank_opportunities(scan_result)

    # Higher expected_return wins first (hierarchy step 3, before risk at step 4) -
    # this is the declared, explicit ordering, not a reward/risk ratio.
    assert [r.symbol for r in result.ranked] == ["HIGH_RETURN_HIGH_RISK", "LOW_RETURN_LOW_RISK"]


# ── data sufficiency ─────────────────────────────────────────────────────


def test_insufficient_data_cannot_promote_a_symbol_above_a_well_supported_one():
    scan_result = _scan_result(
        successful=[
            # Numerically "better" confidence, but data_sufficiency is
            # too low - classify_opportunity (Phase B) demotes this to
            # WATCH regardless.
            _success("UNDER_SUPPORTED", decision=Prediction.BUY, confidence=0.95, data_sufficiency=0.1),
            _success("WELL_SUPPORTED", decision=Prediction.BUY, confidence=0.6, data_sufficiency=1.0),
        ]
    )
    result = rank_opportunities(scan_result)

    assert result.ranked[0].symbol == "WELL_SUPPORTED"
    assert result.ranked[0].assessment.classification == OpportunityLabel.BUY_BIAS
    assert result.ranked[1].symbol == "UNDER_SUPPORTED"
    assert result.ranked[1].assessment.classification == OpportunityLabel.WATCH


# ── deterministic tie-breaking by symbol ─────────────────────────────────


def test_fully_equal_opportunities_use_symbol_as_the_final_tiebreaker():
    scan_result = _scan_result(
        successful=[
            _success("MSFT", decision=Prediction.BUY, confidence=0.6, expected_return=5.0, expected_volatility=8.0),
            _success("AAPL", decision=Prediction.BUY, confidence=0.6, expected_return=5.0, expected_volatility=8.0),
        ]
    )
    result = rank_opportunities(scan_result)

    assert [r.symbol for r in result.ranked] == ["AAPL", "MSFT"]


# ── failure handling ─────────────────────────────────────────────────────


def test_failed_scan_results_are_excluded_from_ranking_but_reported():
    scan_result = _scan_result(
        successful=[_success("AAPL")],
        failed=[_failure("INVALID", error_type="InsufficientPriceDataError")],
    )
    result = rank_opportunities(scan_result)

    assert result.ranked_count == 1
    assert result.ranked[0].symbol == "AAPL"
    assert result.failed_symbols == ["INVALID"]
    assert result.total_scanned_count == 2


def test_all_symbols_failed_produces_an_empty_but_valid_ranking():
    scan_result = _scan_result(failed=[_failure("BAD1"), _failure("BAD2")])
    result = rank_opportunities(scan_result)

    assert result.ranked == []
    assert result.ranked_count == 0
    assert sorted(result.failed_symbols) == ["BAD1", "BAD2"]


def test_unclassifiable_symbol_is_excluded_without_crashing_the_whole_ranking(monkeypatch):
    """Defensive path: even if classify_opportunity somehow raised for
    one symbol, the rest of the batch must still be ranked."""
    import intelligence.opportunity_ranking as ranking_module

    real_classify = ranking_module.classify_opportunity

    def _flaky_classify(decision_output, config=None):
        if decision_output.symbol == "BROKEN":
            raise ValueError("simulated classification failure")
        return real_classify(decision_output, config)

    monkeypatch.setattr(ranking_module, "classify_opportunity", _flaky_classify)

    scan_result = _scan_result(successful=[_success("BROKEN"), _success("AAPL")])
    result = ranking_module.rank_opportunities(scan_result)

    assert result.ranked_count == 1
    assert result.ranked[0].symbol == "AAPL"
    assert result.unclassifiable_symbols == ["BROKEN"]


# ── traceability ──────────────────────────────────────────────────────


def test_canonical_decision_output_fields_remain_traceable():
    response = _response("AAPL", decision=Prediction.BUY, confidence=0.9)
    scan_result = _scan_result(successful=[ScanSymbolResult(symbol="AAPL", status=ScanSymbolStatus.SUCCESS, response=response, duration_ms=1.0)])

    result = rank_opportunities(scan_result)
    ranked = result.ranked[0]

    assert ranked.response is response  # the exact canonical PipelineResponse, not a copy
    assert ranked.assessment.decision == Prediction.BUY  # the real Decision Engine output stays visible
    assert ranked.assessment.decision == ranked.response.decision


# ── no composite score / no LLM ──────────────────────────────────────────


def test_no_composite_numeric_score_field_exists():
    scan_result = _scan_result(successful=[_success("AAPL")])
    result = rank_opportunities(scan_result)
    ranked = result.ranked[0]

    reason_fields = set(ranked.reason.model_fields.keys())
    assert reason_fields == {"label_priority", "risk_rank"}
    assert not any("score" in field.lower() for field in reason_fields)
    assessment_fields = set(ranked.assessment.model_fields.keys())
    assert not any("score" in field.lower() for field in assessment_fields)


# ── determinism ───────────────────────────────────────────────────────


def test_ranking_is_deterministic_across_repeated_calls():
    scan_result = _scan_result(
        successful=[
            _success("AAPL", confidence=0.9),
            _success("MSFT", decision=Prediction.HOLD),
            _success("NVDA", decision=Prediction.SELL),
        ]
    )

    first = rank_opportunities(scan_result)
    second = rank_opportunities(scan_result)

    assert [r.symbol for r in first.ranked] == [r.symbol for r in second.ranked]
    assert [r.rank for r in first.ranked] == [r.rank for r in second.ranked]


# ── scan_and_rank composition ─────────────────────────────────────────


class _FakeScanner:
    def __init__(self, result: MarketScanResult) -> None:
        self._result = result
        self.scanned_symbols = None

    def scan(self, symbols: List[str]) -> MarketScanResult:
        self.scanned_symbols = symbols
        return self._result


def test_scan_and_rank_composes_scanner_and_ranking():
    scan_result = _scan_result(successful=[_success("AAPL")])
    fake_scanner = _FakeScanner(scan_result)

    result = scan_and_rank(fake_scanner, ["AAPL"])

    assert fake_scanner.scanned_symbols == ["AAPL"]
    assert result.ranked_count == 1
    assert result.ranked[0].symbol == "AAPL"
