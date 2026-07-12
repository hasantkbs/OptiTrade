"""
Unit tests for signals/models.py and signals/technical.py.

Tests verify:
  - Signal field constraints (valid direction/strength/category/timeframe values)
  - normalized_value formula correctness and bounds [0, 1]
  - strength thresholds (STRONG/MODERATE/WEAK)
  - TechnicalSignalEngine.generate() for all indicator families
  - EngineResult aggregation (direction, confidence, aggregate_score)
  - SignalCollection.to_dict() / has_data
  - Edge cases (empty input, zero-delta signals, unknown indicator keys)

No network calls, no filesystem access.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from signals.models import (
    Signal, EngineResult, SignalCollection,
    VALID_DIRECTIONS, VALID_STRENGTHS, VALID_TIMEFRAMES, VALID_CATEGORIES,
)
from signals.technical import TechnicalSignalEngine


# ── Test helpers ──────────────────────────────────────────────────────────────

def _contrib(
    indicator_key: str,
    name: str,
    value,
    score_delta: int,
    reason: str = "test reason",
    max_bullish: int = 14,
    max_bearish: int = 14,
):
    """Build a contribution dict matching the format from core.scoring._contrib()."""
    return {
        "name":          name,
        "indicator_key": indicator_key,
        "value":         value,
        "score_delta":   score_delta,
        "reason":        reason,
        "direction":     "BULLISH" if score_delta > 0 else ("BEARISH" if score_delta < 0 else "NEUTRAL"),
        "max_bullish":   max_bullish,
        "max_bearish":   max_bearish,
    }


ENGINE = TechnicalSignalEngine()


# ── Signal field validation ────────────────────────────────────────────────────

class TestSignalFieldValidation:
    def _sample(self, direction="BULLISH", strength="MODERATE", timeframe="SHORT", category="TECHNICAL"):
        return Signal(
            signal_id="rsi_bullish", indicator="RSI",
            value=28.5, normalized_value=0.70,
            direction=direction, strength=strength,
            confidence=0.75, contribution=8.0,
            reason="RSI oversold", timeframe=timeframe, category=category,
        )

    def test_direction_bullish_valid(self):
        assert self._sample(direction="BULLISH").direction == "BULLISH"

    def test_direction_bearish_valid(self):
        assert self._sample(direction="BEARISH").direction == "BEARISH"

    def test_direction_neutral_valid(self):
        assert self._sample(direction="NEUTRAL").direction == "NEUTRAL"

    def test_all_valid_strengths(self):
        for s in VALID_STRENGTHS:
            sig = self._sample(strength=s)
            assert sig.strength == s

    def test_all_valid_timeframes(self):
        for tf in VALID_TIMEFRAMES:
            sig = self._sample(timeframe=tf)
            assert sig.timeframe == tf

    def test_all_valid_categories(self):
        for cat in VALID_CATEGORIES:
            sig = self._sample(category=cat)
            assert sig.category == cat

    def test_to_dict_returns_dict(self):
        sig = self._sample()
        d = sig.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_all_fields(self):
        sig = self._sample()
        d = sig.to_dict()
        expected = {
            "signal_id", "indicator", "value", "normalized_value",
            "direction", "strength", "confidence", "contribution",
            "reason", "timeframe", "category",
        }
        assert set(d.keys()) == expected

    def test_signal_is_immutable(self):
        sig = self._sample()
        with pytest.raises(Exception):
            sig.direction = "BULLISH"


# ── normalized_value formula ──────────────────────────────────────────────────

class TestNormalizedValue:
    """
    Formula: (delta + max_range) / (2 × max_range)
    where max_range = max(|max_bull|, |max_bear|)
    """

    def test_max_bullish_gives_one(self):
        # RSI extreme oversold: delta=14, max=14 → 1.0
        val = TechnicalSignalEngine._normalized(14.0, 14, 14)
        assert val == 1.0

    def test_max_bearish_gives_zero(self):
        # RSI extreme overbought: delta=-14, max=14 → 0.0
        val = TechnicalSignalEngine._normalized(-14.0, 14, 14)
        assert val == 0.0

    def test_zero_delta_gives_half(self):
        val = TechnicalSignalEngine._normalized(0.0, 14, 14)
        assert val == 0.5

    def test_partial_bullish_is_between_half_and_one(self):
        # delta=8, max=14 → (8+14)/28 = 0.786
        val = TechnicalSignalEngine._normalized(8.0, 14, 14)
        assert 0.5 < val < 1.0

    def test_partial_bearish_is_between_zero_and_half(self):
        # delta=-8, max=14 → (−8+14)/28 = 0.214
        val = TechnicalSignalEngine._normalized(-8.0, 14, 14)
        assert 0.0 < val < 0.5

    def test_result_always_in_01(self):
        for delta in (-100, -14, -8, -2, 0, 2, 8, 14, 100):
            val = TechnicalSignalEngine._normalized(float(delta), 14, 14)
            assert 0.0 <= val <= 1.0, f"delta={delta} gave normalized={val}"

    def test_asymmetric_max_bull_bear(self):
        # balance: max_bullish=5, max_bearish=6 → max_range=6
        # delta=5: (5+6)/12 = 0.917
        val = TechnicalSignalEngine._normalized(5.0, 5, 6)
        assert abs(val - 11/12) < 0.001

    def test_zero_max_range_returns_half(self):
        val = TechnicalSignalEngine._normalized(0.0, 0, 0)
        assert val == 0.5

    def test_macd_bullish_full_strength(self):
        # MACD max=6: delta=6 → (6+6)/12 = 1.0
        val = TechnicalSignalEngine._normalized(6.0, 6, 6)
        assert val == 1.0

    def test_stochastic_moderate(self):
        # delta=4, max=8 → (4+8)/16 = 0.75
        val = TechnicalSignalEngine._normalized(4.0, 8, 8)
        assert abs(val - 0.75) < 0.001


# ── strength computation ──────────────────────────────────────────────────────

class TestStrengthComputation:
    """Thresholds: STRONG ≥ 70%, MODERATE ≥ 35%, else WEAK."""

    def test_full_bullish_is_strong(self):
        assert TechnicalSignalEngine._strength(14.0, 14, 14) == "STRONG"

    def test_full_bearish_is_strong(self):
        assert TechnicalSignalEngine._strength(-14.0, 14, 14) == "STRONG"

    def test_70pct_is_strong_boundary(self):
        # ratio = 9.8/14 = 0.70 → STRONG
        assert TechnicalSignalEngine._strength(9.8, 14, 14) == "STRONG"

    def test_just_below_70pct_is_moderate(self):
        # ratio = 9.5/14 = 0.679 → MODERATE
        assert TechnicalSignalEngine._strength(9.5, 14, 14) == "MODERATE"

    def test_35pct_is_moderate_boundary(self):
        # ratio = 4.9/14 = 0.35 → MODERATE
        assert TechnicalSignalEngine._strength(4.9, 14, 14) == "MODERATE"

    def test_just_below_35pct_is_weak(self):
        # ratio = 4.8/14 = 0.343 → WEAK
        assert TechnicalSignalEngine._strength(4.8, 14, 14) == "WEAK"

    def test_zero_delta_is_weak(self):
        assert TechnicalSignalEngine._strength(0.0, 14, 14) == "WEAK"

    def test_zero_max_range_is_weak(self):
        assert TechnicalSignalEngine._strength(5.0, 0, 0) == "WEAK"

    def test_rsi_oversold_moderate(self):
        # delta=8, max=14 → ratio 0.571 → MODERATE
        assert TechnicalSignalEngine._strength(8.0, 14, 14) == "MODERATE"

    def test_rsi_extreme_oversold_strong(self):
        # delta=14, max=14 → ratio 1.0 → STRONG
        assert TechnicalSignalEngine._strength(14.0, 14, 14) == "STRONG"

    def test_rsi_mild_oversold_weak(self):
        # delta=2, max=14 → ratio 0.143 → WEAK
        assert TechnicalSignalEngine._strength(2.0, 14, 14) == "WEAK"


# ── TechnicalSignalEngine.generate() ─────────────────────────────────────────

class TestEngineGenerate:
    def test_empty_contributions_returns_neutral_result(self):
        result = ENGINE.generate([])
        assert result.direction == "NEUTRAL"
        assert result.signals == []
        assert result.aggregate_score == 0.0

    def test_rsi_bullish_contribution(self):
        contribs = [_contrib("rsi", "RSI", 28.5, 8)]
        result = ENGINE.generate(contribs)
        assert len(result.signals) == 1
        sig = result.signals[0]
        assert sig.direction == "BULLISH"
        assert sig.indicator == "RSI"
        assert sig.value == 28.5
        assert sig.contribution == 8.0
        assert sig.category == "TECHNICAL"
        assert sig.timeframe == "SHORT"

    def test_rsi_bearish_contribution(self):
        contribs = [_contrib("rsi", "RSI", 81.0, -14)]
        result = ENGINE.generate(contribs)
        sig = result.signals[0]
        assert sig.direction == "BEARISH"
        assert sig.contribution == -14.0

    def test_rsi_neutral_zero_delta(self):
        contribs = [_contrib("rsi", "RSI", 51.0, 0)]
        result = ENGINE.generate(contribs)
        sig = result.signals[0]
        assert sig.direction == "NEUTRAL"
        assert sig.normalized_value == 0.5

    def test_macd_contribution_timeframe(self):
        contribs = [_contrib("macd", "MACD", 0.5, 6, max_bullish=6, max_bearish=6)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].timeframe == "MEDIUM"

    def test_bollinger_contribution(self):
        contribs = [_contrib("bollinger", "Bollinger Bands", -0.1, 10, max_bullish=10, max_bearish=10)]
        result = ENGINE.generate(contribs)
        sig = result.signals[0]
        assert sig.direction == "BULLISH"
        assert sig.normalized_value == 1.0   # delta=max_bull=10

    def test_adx_contribution_medium_timeframe(self):
        contribs = [_contrib("adx", "ADX", 30.0, 3, max_bullish=6, max_bearish=6)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].timeframe == "MEDIUM"

    def test_stochastic_contribution(self):
        contribs = [_contrib("stochastic", "Stochastic", 18.0, 8, max_bullish=8, max_bearish=8)]
        result = ENGINE.generate(contribs)
        sig = result.signals[0]
        assert sig.direction == "BULLISH"
        assert sig.normalized_value == 1.0

    def test_williams_r_contribution(self):
        contribs = [_contrib("williams_r", "Williams %R", -85.0, 8, max_bullish=8, max_bearish=8)]
        result = ENGINE.generate(contribs)
        sig = result.signals[0]
        assert sig.direction == "BULLISH"

    def test_cci_contribution(self):
        contribs = [_contrib("cci", "CCI", -160.0, 8, max_bullish=8, max_bearish=8)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].direction == "BULLISH"

    def test_volume_category(self):
        contribs = [_contrib("volume", "Hacim", 2.5, 8, max_bullish=8, max_bearish=8)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].category == "VOLUME"

    def test_balance_category(self):
        contribs = [_contrib("balance", "Bilanço", None, 5, max_bullish=5, max_bearish=6)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].category == "FUNDAMENTAL"

    def test_convergence_category(self):
        contribs = [_contrib("convergence", "Yakınsama Bonusu", 5, 7, max_bullish=7, max_bearish=7)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].category == "META"

    def test_ichimoku_long_timeframe(self):
        contribs = [_contrib("ichimoku", "Ichimoku", None, 8, max_bullish=13, max_bearish=13)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].timeframe == "LONG"

    def test_divergence_high_confidence(self):
        contribs = [_contrib("divergence", "Diverjans", None, 12, max_bullish=12, max_bearish=12)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].confidence == 0.80

    def test_adx_high_confidence(self):
        contribs = [_contrib("adx", "ADX", 35.0, 3, max_bullish=6, max_bearish=6)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].confidence == 0.80

    def test_unknown_indicator_key_uses_defaults(self):
        contribs = [_contrib("unknown_indicator", "Unknown", 1.0, 5)]
        result = ENGINE.generate(contribs)
        sig = result.signals[0]
        assert sig.confidence == 0.60
        assert sig.timeframe == "MEDIUM"
        assert sig.category == "TECHNICAL"

    def test_multiple_contributions_all_become_signals(self):
        contribs = [
            _contrib("rsi", "RSI", 28.0, 8),
            _contrib("macd", "MACD", 0.5, 6, max_bullish=6, max_bearish=6),
            _contrib("stochastic", "Stochastic", 18.0, 8, max_bullish=8, max_bearish=8),
        ]
        result = ENGINE.generate(contribs)
        assert len(result.signals) == 3

    def test_contribution_value_preserved_exactly(self):
        contribs = [_contrib("rsi", "RSI", 28.5, 14)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].contribution == 14.0

    def test_reason_preserved(self):
        contribs = [_contrib("rsi", "RSI", 28.5, 8, reason="RSI asiri satim (28.5)")]
        result = ENGINE.generate(contribs)
        assert result.signals[0].reason == "RSI asiri satim (28.5)"


# ── Signal ID uniqueness for multi-fire indicators ────────────────────────────

class TestSignalId:
    def test_single_occurrence_has_no_suffix(self):
        contribs = [_contrib("ichimoku", "Ichimoku", None, 8, max_bullish=13, max_bearish=13)]
        result = ENGINE.generate(contribs)
        assert result.signals[0].signal_id == "ichimoku_bullish"

    def test_second_occurrence_gets_suffix(self):
        # Ichimoku cloud (BULLISH) + TK cross (BULLISH) — same key, same direction
        contribs = [
            _contrib("ichimoku", "Ichimoku", None, 8, max_bullish=13, max_bearish=13),
            _contrib("ichimoku", "Ichimoku", None, 5, max_bullish=13, max_bearish=13),
        ]
        result = ENGINE.generate(contribs)
        ids = [s.signal_id for s in result.signals]
        assert "ichimoku_bullish" in ids
        assert "ichimoku_bullish_2" in ids

    def test_different_directions_same_key_second_gets_suffix(self):
        # Sequence counter is per-key (not per-key+direction), so the second
        # ichimoku contribution always gets _2 regardless of its direction.
        contribs = [
            _contrib("ichimoku", "Ichimoku", None,  8, max_bullish=13, max_bearish=13),
            _contrib("ichimoku", "Ichimoku", None, -5, max_bullish=13, max_bearish=13),
        ]
        result = ENGINE.generate(contribs)
        ids = [s.signal_id for s in result.signals]
        assert "ichimoku_bullish" in ids
        assert "ichimoku_bearish_2" in ids

    def test_signal_ids_are_unique_in_full_set(self):
        contribs = [
            _contrib("rsi", "RSI", 28.5, 8),
            _contrib("macd", "MACD", 0.5, 6, max_bullish=6, max_bearish=6),
            _contrib("bollinger", "Bollinger Bands", -0.1, 10, max_bullish=10, max_bearish=10),
            _contrib("ichimoku", "Ichimoku", None, 8, max_bullish=13, max_bearish=13),
            _contrib("ichimoku", "Ichimoku", None, 5, max_bullish=13, max_bearish=13),
        ]
        result = ENGINE.generate(contribs)
        ids = [s.signal_id for s in result.signals]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"


# ── EngineResult aggregation ──────────────────────────────────────────────────

class TestEngineAggregation:
    def test_aggregate_score_is_sum_of_contributions(self):
        contribs = [
            _contrib("rsi", "RSI", 28.0, 8),
            _contrib("macd", "MACD", 0.5, 6, max_bullish=6, max_bearish=6),
            _contrib("stochastic", "Stochastic", 18.0, -4, max_bullish=8, max_bearish=8),
        ]
        result = ENGINE.generate(contribs)
        assert result.aggregate_score == 10.0  # 8 + 6 - 4

    def test_aggregate_score_with_negatives(self):
        contribs = [
            _contrib("rsi", "RSI", 82.0, -14),
            _contrib("macd", "MACD", -0.5, -6, max_bullish=6, max_bearish=6),
        ]
        result = ENGINE.generate(contribs)
        assert result.aggregate_score == -20.0

    def test_bullish_when_bull_weight_dominant(self):
        contribs = [
            _contrib("rsi", "RSI", 28.0, 14),      # bull: 14
            _contrib("macd", "MACD", 0.5, 6, max_bullish=6, max_bearish=6),  # bull: 6
            _contrib("stochastic", "Stochastic", 85.0, -4, max_bullish=8, max_bearish=8),  # bear: 4
        ]
        result = ENGINE.generate(contribs)
        # bull_weight=20, bear_weight=4; 20 > 4*1.5=6 → BULLISH
        assert result.direction == "BULLISH"

    def test_bearish_when_bear_weight_dominant(self):
        contribs = [
            _contrib("rsi", "RSI", 82.0, -14),
            _contrib("macd", "MACD", -0.5, -6, max_bullish=6, max_bearish=6),
            _contrib("stochastic", "Stochastic", 20.0, 4, max_bullish=8, max_bearish=8),
        ]
        result = ENGINE.generate(contribs)
        # bear_weight=20, bull_weight=4; 20 > 4*1.5=6 → BEARISH
        assert result.direction == "BEARISH"

    def test_neutral_when_balanced(self):
        contribs = [
            _contrib("rsi", "RSI", 28.0, 8),
            _contrib("macd", "MACD", -0.5, -8, max_bullish=8, max_bearish=8),
        ]
        result = ENGINE.generate(contribs)
        # bull_weight=8, bear_weight=8; neither dominates by 1.5× → NEUTRAL
        assert result.direction == "NEUTRAL"

    def test_confidence_is_weighted_average(self):
        # RSI: contribution=14, confidence=0.75; ADX: contribution=6, confidence=0.80
        contribs = [
            _contrib("rsi", "RSI", 20.0, 14),
            _contrib("adx", "ADX", 35.0, 6, max_bullish=6, max_bearish=6),
        ]
        result = ENGINE.generate(contribs)
        expected = (0.75 * 14 + 0.80 * 6) / (14 + 6)
        assert abs(result.confidence - expected) < 0.01

    def test_confidence_in_valid_range(self):
        contribs = [_contrib("rsi", "RSI", 28.0, 8)]
        result = ENGINE.generate(contribs)
        assert 0.0 <= result.confidence <= 1.0

    def test_engine_field_is_technical(self):
        result = ENGINE.generate([_contrib("rsi", "RSI", 28.0, 8)])
        assert result.engine == "TECHNICAL"

    def test_all_neutral_signals_give_neutral_direction(self):
        # Zero-delta signals (informational only)
        contribs = [
            _contrib("cci", "CCI", 5.0, 0),
            _contrib("adx", "ADX", 22.0, 0),
        ]
        result = ENGINE.generate(contribs)
        assert result.direction == "NEUTRAL"


# ── EngineResult.to_dict() ────────────────────────────────────────────────────

class TestEngineResultToDict:
    def test_to_dict_has_required_keys(self):
        result = ENGINE.generate([_contrib("rsi", "RSI", 28.0, 8)])
        d = result.to_dict()
        required = {"engine", "aggregate_score", "direction", "confidence", "signal_count", "signals"}
        assert required.issubset(d.keys())

    def test_signal_count_matches_signals_list(self):
        contribs = [
            _contrib("rsi", "RSI", 28.0, 8),
            _contrib("macd", "MACD", 0.5, 6, max_bullish=6, max_bearish=6),
        ]
        result = ENGINE.generate(contribs)
        d = result.to_dict()
        assert d["signal_count"] == len(d["signals"])

    def test_signals_are_dicts_not_objects(self):
        result = ENGINE.generate([_contrib("rsi", "RSI", 28.0, 8)])
        d = result.to_dict()
        for sig_dict in d["signals"]:
            assert isinstance(sig_dict, dict)


# ── SignalCollection ──────────────────────────────────────────────────────────

class TestSignalCollection:
    def test_empty_collection_has_no_data(self):
        col = SignalCollection()
        assert not col.has_data

    def test_collection_with_technical_has_data(self):
        col = SignalCollection(technical=ENGINE.generate([]))
        assert col.has_data

    def test_to_dict_empty_is_empty_dict(self):
        col = SignalCollection()
        assert col.to_dict() == {}

    def test_to_dict_with_technical_contains_key(self):
        col = SignalCollection(technical=ENGINE.generate([_contrib("rsi", "RSI", 28.0, 8)]))
        d = col.to_dict()
        assert "technical" in d

    def test_to_dict_omits_none_engines(self):
        col = SignalCollection(technical=ENGINE.generate([]))
        d = col.to_dict()
        assert "fundamental" not in d
        assert "news" not in d


# ── normalized_value is always in [0, 1] across all real scoring constants ────

class TestNormalizedValueRealScenarios:
    """Spot-check every scoring constant from scoring_config.py against the formula."""

    _CASES = [
        # (score_delta, max_bullish, max_bearish, description)
        (14,   14, 14, "RSI extreme oversold"),
        (8,    14, 14, "RSI oversold"),
        (2,    14, 14, "RSI mild oversold"),
        (-2,   14, 14, "RSI mild overbought"),
        (-8,   14, 14, "RSI overbought"),
        (-14,  14, 14, "RSI extreme overbought"),
        (6,     6,  6, "MACD bullish"),
        (-6,    6,  6, "MACD bearish"),
        (2,     2,  2, "MACD hist bullish"),
        (10,   10, 10, "BB below strong"),
        (4,    10, 10, "BB below mild"),
        (-4,   10, 10, "BB above mild"),
        (-10,  10, 10, "BB above strong"),
        (10,   10, 10, "EMA golden cross"),
        (-10,  10, 10, "EMA death cross"),
        (8,     8,  8, "Williams extreme oversold"),
        (-8,    8,  8, "Williams extreme overbought"),
        (8,     8,  8, "CCI extreme oversold"),
        (-8,    8,  8, "CCI extreme overbought"),
        (3,     3,  3, "VWAP below"),
        (-3,    3,  3, "VWAP above"),
        (4,     4,  4, "ROC strong bullish"),
        (-4,    4,  4, "ROC strong bearish"),
        (8,    13, 13, "Ichimoku above cloud"),
        (-8,   13, 13, "Ichimoku below cloud"),
        (5,    13, 13, "Ichimoku TK bullish"),
        (12,   12, 12, "Divergence bullish"),
        (-12,  12, 12, "Divergence bearish"),
        (5,     5,  6, "Balance positive"),
        (-6,    5,  6, "Balance negative"),
        (7,     7,  7, "Convergence strong"),
        (6,     6,  6, "ADX strong trend"),
        (-4,    6,  6, "ADX weak trend"),
        (8,     8,  8, "Stochastic extreme oversold"),
        (-8,    8,  8, "Stochastic extreme overbought"),
        (2,     8,  8, "Stochastic KD bullish"),
    ]

    @pytest.mark.parametrize("delta,max_bull,max_bear,desc", _CASES)
    def test_normalized_in_01(self, delta, max_bull, max_bear, desc):
        val = TechnicalSignalEngine._normalized(float(delta), max_bull, max_bear)
        assert 0.0 <= val <= 1.0, f"{desc}: normalized_value={val} out of [0,1]"
