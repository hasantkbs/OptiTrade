"""
Unit tests for Step 0.2 — ADX and Stochastic scoring + explainability layer.

Tests are organised into three groups:
  1. Config integrity  — every indicator in WEIGHTS has documented constraints
  2. ADX scoring       — all ADX branches fire correctly
  3. Stochastic scoring — all Stochastic branches fire correctly
  4. Contributions     — every fired signal produces a well-formed contribution
  5. Backward compat   — old callers omitting adx/stoch_k/stoch_d still work
  6. Score bounds      — final score never escapes [0, 100]
  7. Determinism       — identical inputs always produce identical outputs

All tests use compute_score() directly with synthetic inputs to keep
tests fast and network-free.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from core.scoring import compute_score
from core.scoring_config import (
    WEIGHTS,
    SCORE_BASE, SCORE_MIN, SCORE_MAX,
    ADX_WEAK_THRESHOLD, ADX_MEDIUM_THRESHOLD, ADX_STRONG_THRESHOLD,
    ADX_WEAK_TREND_DELTA, ADX_MEDIUM_TREND_DELTA, ADX_STRONG_TREND_DELTA,
    STOCH_EXTREME_OVERSOLD_THRESHOLD, STOCH_OVERSOLD_THRESHOLD,
    STOCH_OVERBOUGHT_THRESHOLD, STOCH_EXTREME_OVERBOUGHT_THRESHOLD,
    STOCH_EXTREME_OVERSOLD_DELTA, STOCH_OVERSOLD_DELTA,
    STOCH_OVERBOUGHT_DELTA, STOCH_EXTREME_OVERBOUGHT_DELTA,
    STOCH_KD_BULLISH_DELTA, STOCH_KD_BEARISH_DELTA,
)


# ── Shared baseline call ──────────────────────────────────────────────────────

def base_score(**overrides):
    """
    Call compute_score() with genuinely neutral defaults; override as needed.

    Neutrality notes:
    - rsi=50  → no RSI zone fires
    - macd=None, macd_signal=None → MACD block skipped entirely
      (macd=0.0, signal=0.0 is NOT neutral: 0 > 0 is False → fires bearish)
    - volume_ratio=1.0 → between WEAK (0.4) and ABOVE (1.3) thresholds — no fire
    - balance_status="Notr" → no balance contribution
    - adx=None, stoch_k=None, stoch_d=None → new indicators absent
    """
    defaults = dict(
        current_price=100.0,
        potential_price=None,
        volume_ratio=1.0,
        balance_status="Notr",
        rsi=50.0,
        macd=None,
        macd_signal=None,
        adx=None,
        stoch_k=None,
        stoch_d=None,
    )
    defaults.update(overrides)
    return compute_score(**defaults)


def score_only(**kw):
    """Return just the int score."""
    return base_score(**kw)[0]


def contributions_only(**kw):
    return base_score(**kw)[3]


def fired_keys(**kw):
    """Return the set of indicator_keys that produced a non-zero delta."""
    return {c["indicator_key"] for c in contributions_only(**kw) if c["score_delta"] != 0}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Config integrity
# ══════════════════════════════════════════════════════════════════════════════

class TestScoringConfig:
    def test_adx_in_weights(self):
        assert "adx" in WEIGHTS

    def test_stochastic_in_weights(self):
        assert "stochastic" in WEIGHTS

    def test_all_weights_have_positive_limits(self):
        for key, w in WEIGHTS.items():
            assert w.max_bullish >= 0, f"{key}.max_bullish must be >= 0"
            assert w.max_bearish >= 0, f"{key}.max_bearish must be >= 0"

    def test_all_weights_have_name_and_description(self):
        for key, w in WEIGHTS.items():
            assert w.name, f"{key} has empty name"
            assert w.description, f"{key} has empty description"

    def test_adx_max_weights_match_config_delta(self):
        assert WEIGHTS["adx"].max_bullish == ADX_STRONG_TREND_DELTA
        assert WEIGHTS["adx"].max_bearish == ADX_STRONG_TREND_DELTA

    def test_stochastic_max_weights_match_config_delta(self):
        assert WEIGHTS["stochastic"].max_bullish == STOCH_EXTREME_OVERSOLD_DELTA
        assert WEIGHTS["stochastic"].max_bearish == abs(STOCH_EXTREME_OVERBOUGHT_DELTA)

    def test_score_base_and_bounds(self):
        assert SCORE_BASE == 50
        assert SCORE_MIN == 0
        assert SCORE_MAX == 100


# ══════════════════════════════════════════════════════════════════════════════
# 2. ADX scoring
# ══════════════════════════════════════════════════════════════════════════════

class TestADXScoring:
    """ADX measures trend strength.  Direction = dominant bull/bear count."""

    def _with_bull_setup(self, adx_val):
        """Setup: bullish RSI oversold + adx_val.
        Only one directional indicator so bull_count=1, bear_count=0."""
        return base_score(rsi=25.0, adx=adx_val)

    def _with_bear_setup(self, adx_val):
        """Setup: bearish RSI overbought + adx_val.
        Only one directional indicator so bear_count=1, bull_count=0."""
        return base_score(rsi=75.0, adx=adx_val)

    # ── Weak trend ────────────────────────────────────────────────────────────

    def test_weak_adx_fires_adx_contribution(self):
        assert "adx" in fired_keys(adx=5.0)

    def test_weak_adx_contribution_is_bearish(self):
        contribs = contributions_only(adx=5.0)
        adx_c = next(c for c in contribs if c["indicator_key"] == "adx")
        assert adx_c["direction"] == "BEARISH"
        assert adx_c["score_delta"] == ADX_WEAK_TREND_DELTA

    def test_weak_adx_lowers_final_score(self):
        # Final score with weak ADX must be strictly lower than without it
        score_without = score_only()
        score_with    = score_only(adx=ADX_WEAK_THRESHOLD - 1)
        assert score_with < score_without

    # ── Medium trend ──────────────────────────────────────────────────────────

    def test_medium_adx_bullish_contribution_delta(self):
        # Confirm the contribution's score_delta is exactly ADX_MEDIUM_TREND_DELTA
        _, _, _, contribs = self._with_bull_setup(ADX_MEDIUM_THRESHOLD + 1)
        adx_c = next(c for c in contribs if c["indicator_key"] == "adx")
        assert adx_c["score_delta"] == ADX_MEDIUM_TREND_DELTA

    def test_medium_adx_bearish_contribution_delta(self):
        _, _, _, contribs = self._with_bear_setup(ADX_MEDIUM_THRESHOLD + 1)
        adx_c = next(c for c in contribs if c["indicator_key"] == "adx")
        assert adx_c["score_delta"] == -ADX_MEDIUM_TREND_DELTA

    def test_medium_adx_bullish_raises_final_score(self):
        no_adx   = self._with_bull_setup(None)[0]
        with_adx = self._with_bull_setup(ADX_MEDIUM_THRESHOLD + 1)[0]
        assert with_adx > no_adx

    def test_medium_adx_bearish_lowers_final_score(self):
        no_adx   = self._with_bear_setup(None)[0]
        with_adx = self._with_bear_setup(ADX_MEDIUM_THRESHOLD + 1)[0]
        assert with_adx < no_adx

    def test_medium_adx_balanced_no_direction(self):
        # Truly balanced: rsi=50 fires no direction, macd=None → bull==bear==0
        contribs = contributions_only(adx=30.0)
        adx_c = next((c for c in contribs if c["indicator_key"] == "adx"), None)
        # Should exist (with score_delta=0 and direction NEUTRAL) or not appear at all
        if adx_c is not None:
            assert adx_c["direction"] == "NEUTRAL"
            assert adx_c["score_delta"] == 0

    # ── Strong trend ──────────────────────────────────────────────────────────

    def test_strong_adx_bullish_contribution_delta(self):
        _, _, _, contribs = self._with_bull_setup(ADX_STRONG_THRESHOLD + 5)
        adx_c = next(c for c in contribs if c["indicator_key"] == "adx")
        assert adx_c["score_delta"] == ADX_STRONG_TREND_DELTA

    def test_strong_adx_bearish_contribution_delta(self):
        _, _, _, contribs = self._with_bear_setup(ADX_STRONG_THRESHOLD + 5)
        adx_c = next(c for c in contribs if c["indicator_key"] == "adx")
        assert adx_c["score_delta"] == -ADX_STRONG_TREND_DELTA

    def test_strong_adx_bullish_raises_more_than_medium(self):
        medium = self._with_bull_setup(ADX_MEDIUM_THRESHOLD + 1)[0]
        strong = self._with_bull_setup(ADX_STRONG_THRESHOLD + 5)[0]
        assert strong > medium

    def test_strong_adx_contribution_direction_matches_setup(self):
        _, _, _, contribs = self._with_bull_setup(ADX_STRONG_THRESHOLD + 5)
        adx_c = next(c for c in contribs if c["indicator_key"] == "adx")
        assert adx_c["direction"] == "BULLISH"

    # ── No ADX ───────────────────────────────────────────────────────────────

    def test_none_adx_not_in_contributions(self):
        assert "adx" not in fired_keys()

    def test_none_adx_score_unchanged(self):
        s_with    = score_only(adx=None)
        s_without = score_only()
        assert s_with == s_without

    # ── Threshold boundaries ──────────────────────────────────────────────────

    def test_adx_exactly_at_weak_threshold_no_penalty(self):
        # ADX == 20 falls in the uncertain zone (not < 20), should not penalise
        s_weak   = score_only(adx=ADX_WEAK_THRESHOLD - 0.1)
        s_at     = score_only(adx=float(ADX_WEAK_THRESHOLD))
        # at threshold → no penalty, so should be higher than just-below
        assert s_at > s_weak


# ══════════════════════════════════════════════════════════════════════════════
# 3. Stochastic scoring
# ══════════════════════════════════════════════════════════════════════════════

class TestStochasticScoring:

    # ── Extreme oversold ──────────────────────────────────────────────────────

    def test_extreme_oversold_contribution_delta(self):
        _, _, _, contribs = base_score(stoch_k=STOCH_EXTREME_OVERSOLD_THRESHOLD - 1)
        stoch_c = next(c for c in contribs if c["indicator_key"] == "stochastic")
        assert stoch_c["score_delta"] == STOCH_EXTREME_OVERSOLD_DELTA

    def test_extreme_oversold_raises_final_score(self):
        baseline   = score_only()
        with_stoch = score_only(stoch_k=STOCH_EXTREME_OVERSOLD_THRESHOLD - 1)
        assert with_stoch > baseline

    def test_extreme_oversold_direction_is_bullish(self):
        contribs = contributions_only(stoch_k=10.0)
        stoch_c = next(c for c in contribs if c["indicator_key"] == "stochastic")
        assert stoch_c["direction"] == "BULLISH"
        assert stoch_c["score_delta"] == STOCH_EXTREME_OVERSOLD_DELTA

    # ── Oversold (not extreme) ────────────────────────────────────────────────

    def test_oversold_contribution_delta(self):
        _, _, _, contribs = base_score(stoch_k=25.0)
        stoch_c = next(c for c in contribs if c["indicator_key"] == "stochastic")
        assert stoch_c["score_delta"] == STOCH_OVERSOLD_DELTA

    def test_oversold_raises_score(self):
        baseline   = score_only()
        with_stoch = score_only(stoch_k=25.0)
        assert with_stoch > baseline

    # ── Extreme overbought ────────────────────────────────────────────────────

    def test_extreme_overbought_subtracts_max_bearish(self):
        # Verify the contribution delta, not the final score: the session blend
        # (0.70 × base + 0.30 × session_adj) is non-linear so the final integer
        # score may differ by ±1 from the raw delta.
        _, _, _, contribs = base_score(stoch_k=STOCH_EXTREME_OVERBOUGHT_THRESHOLD + 1)
        stoch_c = next(c for c in contribs if c["indicator_key"] == "stochastic")
        assert stoch_c["score_delta"] == STOCH_EXTREME_OVERBOUGHT_DELTA

    def test_extreme_overbought_direction_is_bearish(self):
        contribs = contributions_only(stoch_k=90.0)
        stoch_c = next(c for c in contribs if c["indicator_key"] == "stochastic")
        assert stoch_c["direction"] == "BEARISH"

    # ── Overbought (not extreme) ──────────────────────────────────────────────

    def test_overbought_contribution_delta(self):
        _, _, _, contribs = base_score(stoch_k=75.0)
        stoch_c = next(c for c in contribs if c["indicator_key"] == "stochastic")
        assert stoch_c["score_delta"] == STOCH_OVERBOUGHT_DELTA

    def test_overbought_lowers_score(self):
        baseline   = score_only()
        with_stoch = score_only(stoch_k=75.0)
        assert with_stoch < baseline

    # ── %K/%D crossover momentum ──────────────────────────────────────────────

    def test_kd_bullish_crossover_contribution_delta(self):
        # %K=55 (neutral zone) + %K > %D → should fire KD_BULLISH_DELTA
        _, _, _, contribs = base_score(stoch_k=55.0, stoch_d=45.0)
        stoch_c = next(c for c in contribs if c["indicator_key"] == "stochastic")
        assert stoch_c["score_delta"] == STOCH_KD_BULLISH_DELTA

    def test_kd_bearish_crossover_contribution_delta(self):
        _, _, _, contribs = base_score(stoch_k=45.0, stoch_d=55.0)
        stoch_c = next(c for c in contribs if c["indicator_key"] == "stochastic")
        assert stoch_c["score_delta"] == STOCH_KD_BEARISH_DELTA

    def test_kd_bullish_raises_score(self):
        baseline   = score_only()
        with_stoch = score_only(stoch_k=55.0, stoch_d=45.0)
        assert with_stoch > baseline

    def test_kd_bearish_lowers_score(self):
        baseline   = score_only()
        with_stoch = score_only(stoch_k=45.0, stoch_d=55.0)
        assert with_stoch < baseline

    def test_kd_crossover_not_fired_in_extreme_zone(self):
        # When extreme oversold is already firing, KD cross should NOT stack
        _, _, _, contribs = base_score(stoch_k=10.0, stoch_d=5.0)
        stoch_entries = [c for c in contribs if c["indicator_key"] == "stochastic"]
        # Should be exactly one stoch contribution (the extreme oversold one)
        assert len(stoch_entries) == 1
        assert stoch_entries[0]["score_delta"] == STOCH_EXTREME_OVERSOLD_DELTA

    # ── Neutral zone ──────────────────────────────────────────────────────────

    def test_neutral_stoch_k_no_contribution(self):
        # %K=50, %D=50 → no delta
        assert "stochastic" not in fired_keys(stoch_k=50.0, stoch_d=50.0)

    def test_none_stoch_k_not_in_contributions(self):
        assert "stochastic" not in fired_keys()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Contributions format
# ══════════════════════════════════════════════════════════════════════════════

class TestContributionsFormat:
    REQUIRED_KEYS = {"name", "indicator_key", "value", "score_delta",
                     "reason", "direction", "max_bullish", "max_bearish"}

    def test_every_contribution_has_required_keys(self):
        _, _, _, contribs = base_score(rsi=25.0, macd=1.0, macd_signal=0.5, adx=30.0, stoch_k=10.0)
        for c in contribs:
            missing = self.REQUIRED_KEYS - set(c.keys())
            assert not missing, f"Contribution missing keys: {missing}\n  entry={c}"

    def test_direction_is_one_of_three_values(self):
        _, _, _, contribs = base_score(
            rsi=25.0, macd=1.0, macd_signal=0.5,
            adx=30.0, stoch_k=10.0, stoch_d=8.0,
        )
        for c in contribs:
            assert c["direction"] in {"BULLISH", "BEARISH", "NEUTRAL"}, \
                f"Unknown direction '{c['direction']}' in {c}"

    def test_delta_sign_matches_direction(self):
        _, _, _, contribs = base_score(
            rsi=25.0, macd=1.0, macd_signal=0.5,
            adx=30.0, stoch_k=10.0, stoch_d=8.0,
        )
        for c in contribs:
            if c["direction"] == "BULLISH":
                assert c["score_delta"] > 0, f"BULLISH entry has delta={c['score_delta']}: {c}"
            elif c["direction"] == "BEARISH":
                assert c["score_delta"] < 0, f"BEARISH entry has delta={c['score_delta']}: {c}"

    def test_max_bullish_is_non_negative(self):
        _, _, _, contribs = base_score(rsi=25.0, adx=35.0, stoch_k=15.0)
        for c in contribs:
            assert c["max_bullish"] >= 0

    def test_max_bearish_is_non_negative(self):
        _, _, _, contribs = base_score(rsi=75.0, adx=35.0, stoch_k=85.0)
        for c in contribs:
            assert c["max_bearish"] >= 0

    def test_return_is_four_tuple(self):
        result = compute_score(
            current_price=100.0, potential_price=None,
            volume_ratio=1.0, balance_status="Notr",
            rsi=50.0, macd=0.0, macd_signal=0.0,
        )
        assert len(result) == 4
        score, long, short, contribs = result
        assert isinstance(score, int)
        assert isinstance(long, list)
        assert isinstance(short, list)
        assert isinstance(contribs, list)

    def test_empty_contributions_when_all_neutral(self):
        # rsi=50 (no zone), macd=None (skipped), volume=1.0 (between thresholds),
        # no adx/stoch — nothing should fire
        _, _, _, contribs = base_score()
        non_zero = [c for c in contribs if c["score_delta"] != 0]
        assert non_zero == [], f"Expected no contributions, got: {non_zero}"


# ══════════════════════════════════════════════════════════════════════════════
# 5. Backward compatibility
# ══════════════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """Verify callers that omit adx/stoch_k/stoch_d still work correctly."""

    def test_old_signature_without_adx_stoch(self):
        result = compute_score(
            current_price=100.0,
            potential_price=None,
            volume_ratio=1.0,
            balance_status="Notr",
            rsi=25.0,
            macd=1.0,
            macd_signal=0.5,
        )
        assert len(result) == 4

    def test_old_signature_score_unchanged_no_adx(self):
        s_old = compute_score(
            current_price=100.0, potential_price=None,
            volume_ratio=1.0, balance_status="Notr",
            rsi=25.0, macd=1.0, macd_signal=0.5,
        )[0]
        s_new = compute_score(
            current_price=100.0, potential_price=None,
            volume_ratio=1.0, balance_status="Notr",
            rsi=25.0, macd=1.0, macd_signal=0.5,
            adx=None, stoch_k=None, stoch_d=None,
        )[0]
        assert s_old == s_new

    def test_existing_rsi_contribution_delta_unchanged(self):
        """RSI extreme oversold contribution_delta must still equal RSI_EXTREME_OVERSOLD_DELTA."""
        from core.scoring_config import RSI_EXTREME_OVERSOLD_DELTA
        _, _, _, contribs = base_score(rsi=15.0)
        rsi_c = next(c for c in contribs if c["indicator_key"] == "rsi")
        assert rsi_c["score_delta"] == RSI_EXTREME_OVERSOLD_DELTA

    def test_existing_rsi_raises_final_score(self):
        from core.scoring_config import RSI_EXTREME_OVERSOLD_DELTA
        score_neutral  = score_only()
        score_oversold = score_only(rsi=15.0)
        assert score_oversold > score_neutral

    def test_existing_macd_contribution_delta_unchanged(self):
        from core.scoring_config import MACD_BULLISH_DELTA
        _, _, _, contribs = base_score(macd=1.0, macd_signal=0.5)
        macd_c = next(c for c in contribs if c["indicator_key"] == "macd")
        assert macd_c["score_delta"] == MACD_BULLISH_DELTA

    def test_existing_macd_raises_final_score(self):
        score_neutral   = score_only()
        score_macd_bull = score_only(macd=1.0, macd_signal=0.5)
        assert score_macd_bull > score_neutral


# ══════════════════════════════════════════════════════════════════════════════
# 6. Score bounds
# ══════════════════════════════════════════════════════════════════════════════

class TestScoreBounds:

    def test_max_bullish_inputs_clamped_to_100(self):
        s = score_only(
            rsi=15.0,            # extreme oversold +14
            macd=1.0,            # +6
            macd_signal=0.0,
            volume_ratio=3.0,    # high volume
            adx=45.0,            # very strong
            stoch_k=10.0,        # extreme oversold
        )
        assert s <= SCORE_MAX

    def test_max_bearish_inputs_clamped_to_0(self):
        s = score_only(
            rsi=85.0,            # extreme overbought
            macd=0.0,            # below signal
            macd_signal=1.0,
            volume_ratio=3.0,
            adx=45.0,            # strong but bear direction
            stoch_k=90.0,        # extreme overbought
        )
        assert s >= SCORE_MIN

    def test_score_is_integer(self):
        s = score_only(rsi=25.0, adx=30.0, stoch_k=15.0)
        assert isinstance(s, int)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Determinism
# ══════════════════════════════════════════════════════════════════════════════

class TestDeterminism:

    def test_identical_inputs_identical_outputs(self):
        kwargs = dict(rsi=35.0, macd=0.5, macd_signal=0.3, adx=28.0, stoch_k=25.0, stoch_d=30.0)
        r1 = base_score(**kwargs)
        r2 = base_score(**kwargs)
        assert r1[0] == r2[0]
        assert r1[3] == r2[3]

    def test_contributions_order_is_stable(self):
        kwargs = dict(rsi=35.0, adx=28.0, stoch_k=25.0, stoch_d=30.0)
        _, _, _, c1 = base_score(**kwargs)
        _, _, _, c2 = base_score(**kwargs)
        keys1 = [c["indicator_key"] for c in c1]
        keys2 = [c["indicator_key"] for c in c2]
        assert keys1 == keys2
