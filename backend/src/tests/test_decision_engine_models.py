"""Tests for decision_engine/models.py."""
import pytest
from pydantic import ValidationError

from decision_engine.models import DecisionOutput, EngineVote, Prediction


def _vote(**overrides):
    defaults = dict(
        engine_name="TechnicalEngine", engine_version="v1",
        prediction=Prediction.BUY, confidence=0.8,
        expected_return=1.5, volatility=2.0, evidence=["RSI oversold"],
    )
    defaults.update(overrides)
    return EngineVote(**defaults)


def test_engine_vote_defaults():
    vote = _vote()
    assert vote.timestamp.tzinfo is not None
    assert vote.evidence == ["RSI oversold"]


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_engine_vote_confidence_out_of_range_rejected(confidence):
    with pytest.raises(ValidationError):
        _vote(confidence=confidence)


@pytest.mark.parametrize("field", ["engine_name", "engine_version"])
def test_engine_vote_rejects_blank_identity_fields(field):
    with pytest.raises(ValidationError):
        _vote(**{field: "  "})


def test_engine_vote_accepts_boundary_confidences():
    assert _vote(confidence=0.0).confidence == 0.0
    assert _vote(confidence=1.0).confidence == 1.0


def _decision_output(**overrides):
    defaults = dict(
        symbol="BTC-USD", decision=Prediction.BUY, confidence=0.7,
        expected_return=1.2, expected_volatility=3.0,
        aggregation_strategy_version="accuracy_weighted_v1",
        data_sufficiency=1.0, evidence=["TechnicalEngine: RSI oversold"],
        engine_results=[_vote()],
    )
    defaults.update(overrides)
    return DecisionOutput(**defaults)


def test_decision_output_defaults():
    output = _decision_output()
    assert output.decision == Prediction.BUY
    assert len(output.engine_results) == 1
    assert output.timestamp.tzinfo is not None


@pytest.mark.parametrize("field,value", [("confidence", 1.5), ("data_sufficiency", -0.1)])
def test_decision_output_range_fields_rejected_out_of_bounds(field, value):
    with pytest.raises(ValidationError):
        _decision_output(**{field: value})


def test_decision_output_requires_symbol():
    with pytest.raises(ValidationError):
        DecisionOutput(
            decision=Prediction.HOLD, confidence=0.0, expected_return=0.0,
            expected_volatility=0.0, aggregation_strategy_version="v1",
            data_sufficiency=0.0,
        )
