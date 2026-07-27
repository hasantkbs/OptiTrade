"""Tests for decision_engine/validation.py."""
import math

from decision_engine.models import EngineVote, Prediction
from decision_engine.validation import validate_vote


def _vote(**overrides):
    defaults = dict(
        engine_name="TechnicalEngine", engine_version="v1",
        prediction=Prediction.BUY, confidence=0.8,
        expected_return=1.5, volatility=2.0,
    )
    defaults.update(overrides)
    return EngineVote(**defaults)


def test_valid_vote_passes():
    result = validate_vote(_vote())
    assert result.is_valid is True
    assert result.errors == []


def test_nan_expected_return_rejected():
    result = validate_vote(_vote(expected_return=math.nan))
    assert result.is_valid is False
    assert any("expected_return is NaN" in e for e in result.errors)


def test_infinite_expected_return_rejected():
    result = validate_vote(_vote(expected_return=math.inf))
    assert result.is_valid is False
    assert any("infinite" in e for e in result.errors)


def test_nan_volatility_rejected():
    result = validate_vote(_vote(volatility=math.nan))
    assert result.is_valid is False
    assert any("volatility is NaN" in e for e in result.errors)


def test_negative_volatility_rejected():
    result = validate_vote(_vote(volatility=-1.0))
    assert result.is_valid is False
    assert any("non-negative" in e for e in result.errors)


def test_zero_volatility_is_valid():
    result = validate_vote(_vote(volatility=0.0))
    assert result.is_valid is True


def test_multiple_errors_are_all_reported():
    result = validate_vote(_vote(expected_return=math.nan, volatility=-5.0))
    assert result.is_valid is False
    assert len(result.errors) == 2
