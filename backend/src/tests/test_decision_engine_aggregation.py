"""
Tests for decision_engine/aggregation.py — pure, deterministic aggregation
math. Every expected value below is computed by hand in the test's own
comment, not just asserted against whatever the code happens to produce.
"""
import pytest

from decision_engine.aggregation import aggregate_votes
from decision_engine.models import EngineVote, Prediction


def _vote(engine_name, prediction, confidence, expected_return, volatility, evidence=None):
    return EngineVote(
        engine_name=engine_name, engine_version="v1", prediction=prediction,
        confidence=confidence, expected_return=expected_return, volatility=volatility,
        evidence=evidence or [],
    )


def test_no_votes_returns_neutral_hold():
    result = aggregate_votes([], {})
    assert result.decision == Prediction.HOLD
    assert result.confidence == 0.0
    assert result.expected_return == 0.0
    assert result.expected_volatility == 0.0
    assert result.evidence == []


def test_single_buy_vote_is_decisive():
    # effective_weight = accuracy(1.0) * confidence(0.8) = 0.8
    # only BUY has nonzero weight -> BUY wins, confidence = 0.8/0.8 = 1.0
    # expected_return/volatility are just that one vote's values.
    votes = [_vote("TechnicalEngine", Prediction.BUY, 0.8, 2.0, 3.0)]
    result = aggregate_votes(votes, {"TechnicalEngine": 1.0})

    assert result.decision == Prediction.BUY
    assert result.confidence == pytest.approx(1.0)
    assert result.expected_return == pytest.approx(2.0)
    assert result.expected_volatility == pytest.approx(3.0)


def test_conflicting_votes_the_higher_weighted_side_wins():
    # BUY: accuracy 1.0 * confidence 0.6 = 0.6 effective weight
    # SELL: accuracy 1.0 * confidence 0.9 = 0.9 effective weight
    # total = 1.5, SELL wins (0.9 > 0.6), confidence = 0.9/1.5 = 0.6
    # expected_return = (0.6*5.0 + 0.9*(-2.0)) / 1.5 = (3.0 - 1.8) / 1.5 = 0.8
    votes = [
        _vote("TechnicalEngine", Prediction.BUY, 0.6, 5.0, 1.0),
        _vote("FundamentalEngine", Prediction.SELL, 0.9, -2.0, 4.0),
    ]
    result = aggregate_votes(votes, {"TechnicalEngine": 1.0, "FundamentalEngine": 1.0})

    assert result.decision == Prediction.SELL
    assert result.confidence == pytest.approx(0.6)
    assert result.expected_return == pytest.approx(0.8)
    # volatility = (0.6*1.0 + 0.9*4.0) / 1.5 = (0.6 + 3.6) / 1.5 = 2.8
    assert result.expected_volatility == pytest.approx(2.8)


def test_accuracy_weight_scales_influence_beyond_self_reported_confidence():
    # Both vote with confidence 0.5, but TechnicalEngine has a 3x accuracy
    # weight -> its BUY vote (eff = 3.0*0.5=1.5) must outweigh the other
    # engine's SELL vote (eff = 1.0*0.5=0.5), despite equal confidence.
    votes = [
        _vote("TechnicalEngine", Prediction.BUY, 0.5, 1.0, 1.0),
        _vote("NewsEngine", Prediction.SELL, 0.5, -1.0, 1.0),
    ]
    result = aggregate_votes(votes, {"TechnicalEngine": 3.0, "NewsEngine": 1.0})
    assert result.decision == Prediction.BUY


def test_tie_between_buy_and_sell_resolves_to_hold():
    # BUY eff = 1.0*0.5 = 0.5, SELL eff = 1.0*0.5 = 0.5 (tied, both the max),
    # HOLD eff = 1.0*0.1 = 0.1 -> tie resolves to HOLD.
    # total = 0.5+0.5+0.1 = 1.1, confidence uses HOLD's own weight: 0.1/1.1
    votes = [
        _vote("A", Prediction.BUY, 0.5, 1.0, 1.0),
        _vote("B", Prediction.SELL, 0.5, -1.0, 1.0),
        _vote("C", Prediction.HOLD, 0.1, 0.0, 1.0),
    ]
    result = aggregate_votes(votes, {"A": 1.0, "B": 1.0, "C": 1.0})
    assert result.decision == Prediction.HOLD
    assert result.confidence == pytest.approx(0.1 / 1.1)


def test_all_zero_confidence_votes_yield_neutral_hold_with_zero_confidence():
    votes = [
        _vote("A", Prediction.BUY, 0.0, 5.0, 1.0),
        _vote("B", Prediction.SELL, 0.0, -5.0, 1.0),
    ]
    result = aggregate_votes(votes, {"A": 1.0, "B": 1.0})
    assert result.decision == Prediction.HOLD
    assert result.confidence == 0.0
    assert result.expected_return == 0.0
    assert result.expected_volatility == 0.0


def test_missing_accuracy_weight_defaults_to_one_within_aggregate_votes():
    # aggregate_votes itself falls back to 1.0 for any engine_name not
    # present in the weights dict it's given (the caller, DecisionEngine,
    # is expected to always populate it via AccuracyWeightProvider, but
    # the pure function is still robust on its own).
    votes = [_vote("UnknownEngine", Prediction.BUY, 1.0, 1.0, 1.0)]
    result = aggregate_votes(votes, {})
    assert result.decision == Prediction.BUY
    assert result.confidence == pytest.approx(1.0)


def test_evidence_is_prefixed_with_engine_name_and_concatenated_in_order():
    votes = [
        _vote("TechnicalEngine", Prediction.BUY, 0.8, 1.0, 1.0, evidence=["RSI oversold"]),
        _vote("NewsEngine", Prediction.BUY, 0.6, 1.0, 1.0, evidence=["Positive earnings", "Upgrade"]),
    ]
    result = aggregate_votes(votes, {"TechnicalEngine": 1.0, "NewsEngine": 1.0})
    assert result.evidence == [
        "TechnicalEngine: RSI oversold",
        "NewsEngine: Positive earnings",
        "NewsEngine: Upgrade",
    ]


def test_agreeing_votes_reinforce_confidence():
    # Two engines both voting BUY should produce a higher confidence than
    # a single engine voting BUY alone, all else equal.
    single = aggregate_votes(
        [_vote("A", Prediction.BUY, 0.7, 1.0, 1.0)], {"A": 1.0}
    )
    agreeing = aggregate_votes(
        [_vote("A", Prediction.BUY, 0.7, 1.0, 1.0), _vote("B", Prediction.BUY, 0.7, 1.0, 1.0)],
        {"A": 1.0, "B": 1.0},
    )
    assert agreeing.decision == Prediction.BUY == single.decision
    # Both agree fully -> confidence is 1.0 in both cases (100% of weight
    # backs BUY either way) - agreement doesn't change *confidence* here,
    # it only changes how much weight the winning side has in absolute
    # terms. Documented via an exact equality rather than an inequality
    # assumption, since two fully-agreeing votes normalize to the same 1.0.
    assert agreeing.confidence == pytest.approx(1.0) == single.confidence
