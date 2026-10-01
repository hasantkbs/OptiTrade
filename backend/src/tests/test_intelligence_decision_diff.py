"""
Tests for intelligence/decision_diff.py.

`diff_decisions` is a pure function of two `DecisionOutput`s - no
database, no network, no fakes needed for it. `DecisionHistoryDiffService`
is tested separately against a fake repository satisfying
`ExecutionRepositoryProtocol`.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest

from decision_engine.models import DecisionOutput, Prediction
from intelligence.config import IntelligenceConfig
from intelligence.decision_diff import (
    DecisionHistoryDiffService,
    diff_decisions,
    risk_bucket_for_volatility,
)
from intelligence.exceptions import NoDecisionHistoryError
from intelligence.models import ChangeSignificance, RiskBucket

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _decision(**overrides) -> DecisionOutput:
    defaults = dict(
        symbol="AAPL",
        decision=Prediction.BUY,
        confidence=0.8,
        expected_return=5.0,
        expected_volatility=8.0,
        aggregation_strategy_version="test_v1",
        data_sufficiency=1.0,
        evidence=["RSI oversold", "positive earnings surprise"],
        engine_results=[],
        timestamp=_NOW,
    )
    defaults.update(overrides)
    return DecisionOutput(**defaults)


# ── risk_bucket_for_volatility ───────────────────────────────────────────


def test_risk_bucket_boundaries():
    config = IntelligenceConfig()
    assert risk_bucket_for_volatility(0.0, config) == RiskBucket.LOW
    assert risk_bucket_for_volatility(9.99, config) == RiskBucket.LOW
    assert risk_bucket_for_volatility(10.0, config) == RiskBucket.MEDIUM
    assert risk_bucket_for_volatility(24.99, config) == RiskBucket.MEDIUM
    assert risk_bucket_for_volatility(25.0, config) == RiskBucket.HIGH
    assert risk_bucket_for_volatility(-30.0, config) == RiskBucket.HIGH  # magnitude, sign-agnostic


# ── diff_decisions: no previous decision ─────────────────────────────────


def test_no_previous_decision():
    current = _decision()
    change = diff_decisions(current, None)

    assert change.previous_decision is None
    assert change.decision_changed is False
    assert change.confidence_delta is None
    assert change.expected_return_delta is None
    assert change.previous_risk_bucket is None
    assert change.risk_changed is False
    assert change.evidence_changed is False
    assert change.significance == ChangeSignificance.NONE
    assert change.current_decision == Prediction.BUY


# ── diff_decisions: identical decisions ──────────────────────────────────


def test_identical_decisions_produce_no_change():
    current = _decision()
    previous = _decision(timestamp=_NOW - timedelta(hours=1))

    change = diff_decisions(current, previous)

    assert change.decision_changed is False
    assert change.confidence_delta == 0.0
    assert change.confidence_changed_materially is False
    assert change.expected_return_delta == 0.0
    assert change.expected_return_changed_materially is False
    assert change.risk_changed is False
    assert change.evidence_changed is False
    assert change.significance == ChangeSignificance.NONE


# ── diff_decisions: decision transitions ─────────────────────────────────


@pytest.mark.parametrize(
    "previous_decision, current_decision",
    [
        (Prediction.BUY, Prediction.HOLD),
        (Prediction.HOLD, Prediction.SELL),
        (Prediction.BUY, Prediction.SELL),
        (Prediction.SELL, Prediction.BUY),
    ],
)
def test_decision_transitions_are_always_material(previous_decision, current_decision):
    previous = _decision(decision=previous_decision, timestamp=_NOW - timedelta(hours=1))
    current = _decision(decision=current_decision)

    change = diff_decisions(current, previous)

    assert change.decision_changed is True
    assert change.previous_decision == previous_decision
    assert change.current_decision == current_decision
    assert change.significance == ChangeSignificance.MATERIAL


# ── diff_decisions: confidence deltas ─────────────────────────────────────


def test_confidence_increase_detected():
    previous = _decision(confidence=0.5, timestamp=_NOW - timedelta(hours=1))
    current = _decision(confidence=0.9)

    change = diff_decisions(current, previous)

    assert change.confidence_delta == pytest.approx(0.4)
    assert change.confidence_changed_materially is True
    assert change.significance == ChangeSignificance.MATERIAL


def test_confidence_decrease_detected():
    previous = _decision(confidence=0.82, timestamp=_NOW - timedelta(hours=1))
    current = _decision(confidence=0.61)

    change = diff_decisions(current, previous)

    assert change.confidence_delta == pytest.approx(-0.21)
    assert change.confidence_changed_materially is True
    assert change.significance == ChangeSignificance.MATERIAL


def test_small_confidence_change_is_not_material():
    previous = _decision(confidence=0.80, timestamp=_NOW - timedelta(hours=1))
    current = _decision(confidence=0.85)

    change = diff_decisions(current, previous)

    assert change.confidence_changed_materially is False
    assert change.significance == ChangeSignificance.NONE


def test_confidence_change_exactly_at_threshold_is_material():
    config = IntelligenceConfig(material_confidence_delta=0.15)
    previous = _decision(confidence=0.50, timestamp=_NOW - timedelta(hours=1))
    current = _decision(confidence=0.65)  # delta == 0.15, exactly the threshold

    change = diff_decisions(current, previous, config)

    assert change.confidence_changed_materially is True


# ── diff_decisions: expected_return deltas ────────────────────────────────


def test_expected_return_change_detected():
    previous = _decision(expected_return=8.0, timestamp=_NOW - timedelta(hours=1))
    current = _decision(expected_return=2.0)

    change = diff_decisions(current, previous)

    assert change.expected_return_delta == pytest.approx(-6.0)
    assert change.expected_return_changed_materially is True
    assert change.significance == ChangeSignificance.MATERIAL


def test_small_expected_return_change_is_not_material():
    previous = _decision(expected_return=5.0, timestamp=_NOW - timedelta(hours=1))
    current = _decision(expected_return=6.5)

    change = diff_decisions(current, previous)

    assert change.expected_return_changed_materially is False


# ── diff_decisions: risk (volatility bucket) changes ──────────────────────


def test_risk_change_detected_low_to_high():
    previous = _decision(expected_volatility=5.0, timestamp=_NOW - timedelta(hours=1))
    current = _decision(expected_volatility=30.0)

    change = diff_decisions(current, previous)

    assert change.previous_risk_bucket == RiskBucket.LOW
    assert change.current_risk_bucket == RiskBucket.HIGH
    assert change.risk_changed is True
    assert change.significance == ChangeSignificance.MATERIAL


def test_risk_unchanged_within_same_bucket():
    previous = _decision(expected_volatility=6.0, timestamp=_NOW - timedelta(hours=1))
    current = _decision(expected_volatility=9.0)  # still LOW

    change = diff_decisions(current, previous)

    assert change.risk_changed is False


# ── diff_decisions: data sufficiency ──────────────────────────────────────


def test_data_sufficiency_change_is_minor_when_nothing_else_changed():
    previous = _decision(data_sufficiency=1.0, timestamp=_NOW - timedelta(hours=1))
    current = _decision(data_sufficiency=0.34)

    change = diff_decisions(current, previous)

    assert change.data_sufficiency_delta == pytest.approx(-0.66)
    assert change.data_sufficiency_changed_materially is True
    assert change.significance == ChangeSignificance.MINOR


def test_insufficient_data_alone_does_not_escalate_to_material():
    previous = _decision(data_sufficiency=1.0, confidence=0.8, timestamp=_NOW - timedelta(hours=1))
    current = _decision(data_sufficiency=0.0, confidence=0.8)  # no engines voted, nothing else changed

    change = diff_decisions(current, previous)

    assert change.decision_changed is False
    assert change.significance == ChangeSignificance.MINOR


# ── diff_decisions: evidence changes ──────────────────────────────────────


def test_evidence_change_detected_as_minor():
    previous = _decision(evidence=["RSI oversold"], timestamp=_NOW - timedelta(hours=1))
    current = _decision(evidence=["MACD bullish crossover"])

    change = diff_decisions(current, previous)

    assert change.evidence_changed is True
    assert change.decision_changed is False
    assert change.significance == ChangeSignificance.MINOR


def test_evidence_reordering_alone_is_not_a_change():
    previous = _decision(evidence=["A", "B"], timestamp=_NOW - timedelta(hours=1))
    current = _decision(evidence=["B", "A"])

    change = diff_decisions(current, previous)

    assert change.evidence_changed is False
    assert change.significance == ChangeSignificance.NONE


# ── diff_decisions: ordering / timestamp edge cases ───────────────────────


def test_identical_timestamps_do_not_raise():
    previous = _decision(confidence=0.5, timestamp=_NOW)
    current = _decision(confidence=0.9, timestamp=_NOW)

    change = diff_decisions(current, previous)

    assert change.current_timestamp == change.previous_timestamp
    assert change.confidence_changed_materially is True


def test_function_does_not_reorder_by_timestamp():
    """`diff_decisions` trusts the caller's current/previous labeling -
    it never second-guesses which row is chronologically newer."""
    older_looking = _decision(confidence=0.9, timestamp=_NOW - timedelta(hours=1))
    newer_looking = _decision(confidence=0.5, timestamp=_NOW)

    # Deliberately pass the chronologically-newer one as "previous".
    change = diff_decisions(current=older_looking, previous=newer_looking)

    assert change.current_confidence == 0.9
    assert change.previous_confidence == 0.5
    assert change.confidence_delta == pytest.approx(0.4)


# ── DecisionHistoryDiffService ────────────────────────────────────────────


class _FakeExecutionRepository:
    def __init__(self, history_by_symbol: Optional[dict] = None) -> None:
        self._history = history_by_symbol or {}

    def save(self, output: DecisionOutput) -> None:  # pragma: no cover - unused by these tests
        raise NotImplementedError

    def get_recent(self, symbol: str, limit: int = 10) -> List[DecisionOutput]:
        return self._history.get(symbol, [])[:limit]


def test_service_raises_when_symbol_has_no_history():
    service = DecisionHistoryDiffService(repository=_FakeExecutionRepository())
    with pytest.raises(NoDecisionHistoryError):
        service.get_latest_change("AAPL")


def test_service_treats_single_record_as_no_previous_decision():
    only = _decision()
    repo = _FakeExecutionRepository({"AAPL": [only]})
    service = DecisionHistoryDiffService(repository=repo)

    change = service.get_latest_change("AAPL")

    assert change.previous_decision is None
    assert change.significance == ChangeSignificance.NONE


def test_service_diffs_the_two_most_recent_records():
    current = _decision(decision=Prediction.SELL)
    previous = _decision(decision=Prediction.BUY, timestamp=_NOW - timedelta(hours=1))
    # get_recent's real contract (decision_engine.repository.PostgresExecutionRepository)
    # is ORDER BY timestamp DESC - most recent first.
    repo = _FakeExecutionRepository({"AAPL": [current, previous]})
    service = DecisionHistoryDiffService(repository=repo)

    change = service.get_latest_change("aapl")  # lower-case input

    assert change.symbol == "AAPL"
    assert change.current_decision == Prediction.SELL
    assert change.previous_decision == Prediction.BUY
    assert change.decision_changed is True


def test_service_ignores_records_for_other_symbols():
    repo = _FakeExecutionRepository({"AAPL": [_decision(symbol="AAPL")], "MSFT": [_decision(symbol="MSFT")]})
    service = DecisionHistoryDiffService(repository=repo)

    change = service.get_latest_change("AAPL")

    assert change.symbol == "AAPL"
