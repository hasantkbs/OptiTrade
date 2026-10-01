"""
Tests for intelligence/opportunity.py.

`classify_opportunity` is a pure function of one `DecisionOutput` - no
database, no network. `OpportunityIntelligenceService` is tested
separately against a fake repository satisfying
`ExecutionRepositoryProtocol`.
"""
from datetime import datetime, timezone
from typing import List, Optional

import pytest

from decision_engine.models import DecisionOutput, Prediction
from intelligence.config import IntelligenceConfig
from intelligence.exceptions import NoDecisionHistoryError
from intelligence.models import OpportunityLabel, RiskBucket
from intelligence.opportunity import OpportunityIntelligenceService, classify_opportunity

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_CONFIG = IntelligenceConfig()


def _decision(**overrides) -> DecisionOutput:
    defaults = dict(
        symbol="AAPL",
        decision=Prediction.BUY,
        confidence=0.8,
        expected_return=5.0,
        expected_volatility=8.0,  # LOW bucket
        aggregation_strategy_version="test_v1",
        data_sufficiency=1.0,
        evidence=["RSI oversold"],
        engine_results=[],
        timestamp=_NOW,
    )
    defaults.update(overrides)
    return DecisionOutput(**defaults)


# ── the underlying decision always remains visible/traceable ─────────────


@pytest.mark.parametrize("decision", [Prediction.BUY, Prediction.HOLD, Prediction.SELL])
def test_underlying_decision_is_always_preserved(decision):
    output = _decision(decision=decision, confidence=0.9, data_sufficiency=1.0)
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.decision == decision
    assert assessment.symbol == output.symbol
    assert assessment.confidence == output.confidence
    assert assessment.expected_return == output.expected_return
    assert assessment.expected_volatility == output.expected_volatility
    assert assessment.data_sufficiency == output.data_sufficiency
    assert assessment.evidence == output.evidence
    assert assessment.timestamp == output.timestamp
    assert len(assessment.reason_codes) > 0  # every classification explains itself


# ── insufficient data always wins, regardless of decision ────────────────


@pytest.mark.parametrize("decision", [Prediction.BUY, Prediction.HOLD, Prediction.SELL])
def test_insufficient_data_forces_watch(decision):
    output = _decision(decision=decision, confidence=0.95, data_sufficiency=0.1)
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.WATCH
    assert "INSUFFICIENT_DATA" in assessment.reason_codes


def test_data_sufficiency_exactly_at_threshold_is_not_insufficient():
    output = _decision(
        decision=Prediction.HOLD, data_sufficiency=_CONFIG.min_data_sufficiency_for_classification,
    )
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.HOLD
    assert "INSUFFICIENT_DATA" not in assessment.reason_codes


# ── SELL -> RISK_DETERIORATING ────────────────────────────────────────────


def test_sell_signal_is_risk_deteriorating():
    output = _decision(decision=Prediction.SELL, expected_volatility=8.0)  # LOW risk
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.RISK_DETERIORATING
    assert "SELL_SIGNAL" in assessment.reason_codes
    assert "HIGH_VOLATILITY" not in assessment.reason_codes


def test_sell_signal_with_high_volatility_notes_it():
    output = _decision(decision=Prediction.SELL, expected_volatility=40.0)  # HIGH risk
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.RISK_DETERIORATING
    assert "SELL_SIGNAL" in assessment.reason_codes
    assert "HIGH_VOLATILITY" in assessment.reason_codes


# ── HOLD -> HOLD ───────────────────────────────────────────────────────────


def test_hold_signal_is_hold():
    output = _decision(decision=Prediction.HOLD, confidence=0.5)
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.HOLD
    assert "HOLD_SIGNAL" in assessment.reason_codes


# ── BUY -> WATCH / BUY_BIAS / STRONG_BUY_BIAS ─────────────────────────────


def test_low_confidence_buy_is_watch():
    output = _decision(decision=Prediction.BUY, confidence=0.4, data_sufficiency=1.0)
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.WATCH
    assert "LOW_CONFIDENCE_BUY" in assessment.reason_codes


def test_buy_confidence_exactly_at_watch_threshold_is_not_watch():
    output = _decision(
        decision=Prediction.BUY, confidence=_CONFIG.watch_confidence_threshold, data_sufficiency=1.0,
    )
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification != OpportunityLabel.WATCH


def test_strong_buy_requires_high_confidence_and_data_sufficiency_and_non_high_risk():
    output = _decision(
        decision=Prediction.BUY,
        confidence=_CONFIG.strong_buy_confidence_threshold,
        data_sufficiency=_CONFIG.strong_buy_min_data_sufficiency,
        expected_volatility=8.0,  # LOW
    )
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.STRONG_BUY_BIAS
    assert "HIGH_CONFIDENCE_BUY" in assessment.reason_codes
    assert "SUFFICIENT_DATA" in assessment.reason_codes


def test_strong_buy_downgraded_to_buy_bias_when_risk_is_high():
    output = _decision(
        decision=Prediction.BUY,
        confidence=0.95,
        data_sufficiency=1.0,
        expected_volatility=40.0,  # HIGH
    )
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.BUY_BIAS
    assert "HIGH_VOLATILITY" in assessment.reason_codes
    # Never miscast a genuine BUY signal as a deteriorating/sell-flavored label.
    assert assessment.classification != OpportunityLabel.RISK_DETERIORATING


def test_moderate_confidence_buy_is_buy_bias():
    output = _decision(decision=Prediction.BUY, confidence=0.6, data_sufficiency=1.0, expected_volatility=8.0)
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.BUY_BIAS
    assert "BUY_SIGNAL" in assessment.reason_codes


def test_high_confidence_buy_with_low_data_sufficiency_is_not_strong():
    output = _decision(
        decision=Prediction.BUY, confidence=0.95, data_sufficiency=0.4, expected_volatility=8.0,
    )
    assessment = classify_opportunity(output, _CONFIG)

    assert assessment.classification == OpportunityLabel.BUY_BIAS


# ── OpportunityIntelligenceService ────────────────────────────────────────


class _FakeExecutionRepository:
    def __init__(self, history_by_symbol: Optional[dict] = None) -> None:
        self._history = history_by_symbol or {}

    def save(self, output: DecisionOutput) -> None:  # pragma: no cover - unused by these tests
        raise NotImplementedError

    def get_recent(self, symbol: str, limit: int = 10) -> List[DecisionOutput]:
        return self._history.get(symbol, [])[:limit]


def test_service_raises_when_symbol_has_no_history():
    service = OpportunityIntelligenceService(repository=_FakeExecutionRepository())
    with pytest.raises(NoDecisionHistoryError):
        service.classify_latest("AAPL")


def test_service_classifies_the_most_recent_record():
    repo = _FakeExecutionRepository({"AAPL": [_decision(decision=Prediction.HOLD)]})
    service = OpportunityIntelligenceService(repository=repo)

    assessment = service.classify_latest("aapl")

    assert assessment.symbol == "AAPL"
    assert assessment.classification == OpportunityLabel.HOLD
