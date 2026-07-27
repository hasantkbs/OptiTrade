"""
Characterization tests for core/scoring.py.

These tests document the CURRENT behavior of compute_score/get_decision/
get_risk_level exactly as implemented today. Several branches contain
boundary quirks or asymmetries that look like they could be bugs; per
project instruction, those are documented with a comment at the assertion
that exercises them rather than "fixed" — this file is a record of what
the code does, not what it should do.

IMPORTANT — hidden wall-clock dependency:
compute_score() calls core.session_analysis.compute_session_score() without
ever passing a `dt`, so that call always resolves to
core.session_analysis.get_current_session(dt=None) -> datetime.now(TZ_TR).
This means compute_score()'s return value is NOT a pure function of its
parameters: the same technical inputs can produce a different final score
depending on the time of day (Turkey time) the function happens to run,
because 30% of the final score comes from a session-adjusted value that
depends on which of ASIA/LONDON/NY/OVERLAP/CLOSED is currently active
(see core/session_analysis.py, volatility_mult ranges 0.30-1.80). There is
no way for a caller of compute_score() to control or reproduce this.

To keep these tests deterministic (and to isolate the indicator-scoring
arithmetic that is this module's real logic), most tests below patch
core.scoring.compute_session_score to a neutral passthrough that echoes
base_score back unchanged, via the `_neutralize_session` helper. A
dedicated section near the end tests the session integration itself
(exception-fallback and signal-ordering behavior) plus a standalone test
that exercises the *real* session_analysis.compute_session_score with an
explicit `dt` to document, at its source, exactly why compute_score() is
time-dependent.
"""
from datetime import datetime

import pytz

from core.scoring import compute_score, get_decision, get_risk_level
from core.session_analysis import compute_session_score as real_compute_session_score


def _neutralize_session(monkeypatch):
    """Patch out compute_score's hidden call to compute_session_score.

    Echoes base_score back unchanged (0.7*base + 0.3*base == base) and
    returns no extra signals, so tests below characterize only the
    indicator-scoring arithmetic in compute_score itself, not the
    time-of-day-dependent session blend (see module docstring).
    """

    def fake_session_score(*, rsi, macd, macd_signal_val, macd_hist, volume_ratio, base_score):
        return {
            "session_adjusted_score": base_score,
            "session_signals": [],
            "session_code": "LONDON",
        }

    monkeypatch.setattr("core.scoring.compute_session_score", fake_session_score)


def _score(monkeypatch, **overrides):
    """compute_score with session neutralized and sensible neutral defaults."""
    _neutralize_session(monkeypatch)
    params = dict(
        current_price=100.0,
        potential_price=None,
        volume_ratio=1.0,
        balance_status="Notr",
        rsi=None,
        macd=None,
        macd_signal=None,
    )
    params.update(overrides)
    return compute_score(**params)


# ─────────────────────────────────────────────────────────────────────────
# get_decision
# ─────────────────────────────────────────────────────────────────────────

def test_get_decision_boundaries():
    assert get_decision(100) == ("GUCLU AL (LONG)", "STRONG_BUY")
    assert get_decision(78) == ("GUCLU AL (LONG)", "STRONG_BUY")
    assert get_decision(77) == ("AL", "BUY")
    assert get_decision(63) == ("AL", "BUY")
    assert get_decision(62) == ("NOTR / IZLE", "NEUTRAL")
    assert get_decision(50) == ("NOTR / IZLE", "NEUTRAL")
    assert get_decision(38) == ("NOTR / IZLE", "NEUTRAL")
    assert get_decision(37) == ("SAT", "SELL")
    assert get_decision(23) == ("SAT", "SELL")
    assert get_decision(22) == ("GUCLU SAT (SHORT)", "STRONG_SELL")
    assert get_decision(0) == ("GUCLU SAT (SHORT)", "STRONG_SELL")


# ─────────────────────────────────────────────────────────────────────────
# get_risk_level
# ─────────────────────────────────────────────────────────────────────────

def test_get_risk_level_boundaries_use_velocity_when_no_atr():
    assert get_risk_level(price_velocity=0.0, atr_pct=None) == "Dusuk"
    assert get_risk_level(price_velocity=1.5, atr_pct=None) == "Dusuk"      # boundary: not > 1.5
    assert get_risk_level(price_velocity=1.51, atr_pct=None) == "Orta"
    assert get_risk_level(price_velocity=3.5, atr_pct=None) == "Orta"       # boundary: not > 3.5
    assert get_risk_level(price_velocity=3.51, atr_pct=None) == "Yuksek"
    assert get_risk_level(price_velocity=6.0, atr_pct=None) == "Yuksek"     # boundary: not > 6
    assert get_risk_level(price_velocity=6.01, atr_pct=None) == "Cok Yuksek"


def test_get_risk_level_uses_negative_velocity_absolute_value():
    assert get_risk_level(price_velocity=-7.0, atr_pct=None) == "Cok Yuksek"


def test_get_risk_level_uses_the_larger_of_velocity_and_atr():
    # velocity is low but atr_pct is high -> atr_pct wins
    assert get_risk_level(price_velocity=0.1, atr_pct=8.0) == "Cok Yuksek"
    # velocity is high but atr_pct is low -> velocity wins
    assert get_risk_level(price_velocity=7.0, atr_pct=0.1) == "Cok Yuksek"


# ─────────────────────────────────────────────────────────────────────────
# compute_score — baseline
# ─────────────────────────────────────────────────────────────────────────

def test_compute_score_neutral_inputs_return_base_50(monkeypatch):
    score, longs, shorts = _score(monkeypatch)
    assert score == 50
    assert longs == []
    assert shorts == []


def test_compute_score_is_clamped_to_0_100(monkeypatch):
    # Stack every strong-bearish indicator to try to drive the score below 0.
    score, _, _ = _score(
        monkeypatch,
        rsi=95.0, macd=0.1, macd_signal=0.9, bollinger={"percent_b": 1.5},
        ema_crossover="DEATH_CROSS", trend_strength=-20.0, volume_ratio=3.0,
        williams_r=-1.0, cci=300.0, vwap=50.0, current_price=100.0,
        roc=-30.0, ichimoku={"cloud_signal": "BELOW_CLOUD", "tk_cross": "BEARISH"},
        divergence={"divergence": "BEARISH_DIVERGENCE", "description": "x"},
        balance_status="Negatif",
    )
    assert 0 <= score <= 100
    assert score == 0  # this combination is strong enough to floor out


# ─────────────────────────────────────────────────────────────────────────
# Potential price
# ─────────────────────────────────────────────────────────────────────────

def test_potential_price_strong_discount_is_bullish(monkeypatch):
    score, longs, _ = _score(monkeypatch, current_price=80.0, potential_price=100.0)
    assert score == 62  # ratio 0.80 < 0.85 -> +12
    assert any("ucuz" in s for s in longs)


def test_potential_price_weak_discount_is_bullish_but_smaller(monkeypatch):
    score, _, _ = _score(monkeypatch, current_price=90.0, potential_price=100.0)
    assert score == 54  # ratio 0.90, in [0.85, 0.95) -> +4 only (no bull_count)


def test_potential_price_strong_premium_is_bearish(monkeypatch):
    score, _, shorts = _score(monkeypatch, current_price=115.0, potential_price=100.0)
    assert score == 38  # ratio 1.15 > 1.10 -> -12
    assert any("pahali" in s for s in shorts)


def test_potential_price_weak_premium_is_bearish_but_smaller(monkeypatch):
    score, _, _ = _score(monkeypatch, current_price=105.0, potential_price=100.0)
    assert score == 46  # ratio 1.05, in (1.02, 1.10] -> -4 only


def test_potential_price_middle_ratio_has_no_effect(monkeypatch):
    score, longs, shorts = _score(monkeypatch, current_price=100.0, potential_price=100.0)
    assert score == 50
    assert longs == [] and shorts == []


def test_potential_price_zero_or_negative_is_ignored(monkeypatch):
    # `if potential_price and potential_price > 0` - 0 is falsy, negative fails > 0.
    score_zero, _, _ = _score(monkeypatch, potential_price=0.0)
    score_neg, _, _ = _score(monkeypatch, potential_price=-50.0)
    assert score_zero == 50
    assert score_neg == 50


# ─────────────────────────────────────────────────────────────────────────
# RSI
# ─────────────────────────────────────────────────────────────────────────

def test_rsi_extreme_overbought(monkeypatch):
    score, _, shorts = _score(monkeypatch, rsi=85.0)
    assert score == 36  # > 80 -> -14
    assert any("cok asiri alim" in s for s in shorts)


def test_rsi_overbought(monkeypatch):
    score, _, _ = _score(monkeypatch, rsi=75.0)
    assert score == 42  # > 70, <= 80 -> -8


def test_rsi_extreme_oversold(monkeypatch):
    score, longs, _ = _score(monkeypatch, rsi=15.0)
    assert score == 64  # < 20 -> +14
    assert any("cok asiri satim" in s for s in longs)


def test_rsi_oversold(monkeypatch):
    score, _, _ = _score(monkeypatch, rsi=25.0)
    assert score == 58  # < 30, >= 20 -> +8


def test_rsi_mild_zones(monkeypatch):
    assert _score(monkeypatch, rsi=35.0)[0] == 52  # < 40 -> +2
    assert _score(monkeypatch, rsi=65.0)[0] == 48  # > 60 -> -2
    assert _score(monkeypatch, rsi=50.0)[0] == 50  # dead center -> no effect


def test_rsi_boundary_80_is_weak_not_strong_overbought(monkeypatch):
    # `rsi > 80` is strict, so rsi == 80 falls to the `> 70` (weak) branch, -8 not -14.
    assert _score(monkeypatch, rsi=80.0)[0] == 42


def test_rsi_boundary_70_falls_through_to_mild_zone(monkeypatch):
    # `rsi > 70` is strict, so rsi == 70 skips the overbought branch entirely and
    # lands in the unrelated `elif rsi > 60` mild-bearish branch (-2), not -8.
    assert _score(monkeypatch, rsi=70.0)[0] == 48


# ─────────────────────────────────────────────────────────────────────────
# MACD
# ─────────────────────────────────────────────────────────────────────────

def test_macd_above_signal_is_bullish(monkeypatch):
    score, longs, _ = _score(monkeypatch, macd=0.5, macd_signal=0.2)
    assert score == 56
    assert any("yukselis" in s for s in longs)


def test_macd_below_signal_is_bearish(monkeypatch):
    score, _, shorts = _score(monkeypatch, macd=0.2, macd_signal=0.5)
    assert score == 44
    assert any("dusus" in s for s in shorts)


def test_macd_equal_to_signal_is_treated_as_bearish(monkeypatch):
    # `if macd > macd_signal: ... else: ...` has no equality case - an exact
    # tie falls into the bearish `else` branch. Documented as-is.
    score, _, shorts = _score(monkeypatch, macd=0.3, macd_signal=0.3)
    assert score == 44
    assert any("dusus" in s for s in shorts)


def test_macd_histogram_momentum_adds_or_subtracts(monkeypatch):
    up_score, _, _ = _score(monkeypatch, macd=0.1, macd_signal=0.05, macd_hist=0.2)
    down_score, _, _ = _score(monkeypatch, macd=0.1, macd_signal=0.05, macd_hist=-0.2)
    assert up_score == 58    # +6 (crossover) + 2 (hist momentum)
    assert down_score == 54  # +6 (crossover) - 2 (hist momentum)


def test_macd_histogram_uses_fallback_denominator_when_macd_is_exactly_zero(monkeypatch):
    # The histogram threshold is `0.05 * abs(macd if macd else 0.001)`. Since
    # 0.0 is falsy in Python, macd == 0.0 (not just macd is None) silently
    # substitutes 0.001, making the threshold an unintended 0.00005 instead
    # of 0.0 - so a tiny histogram value triggers the momentum bonus only
    # when macd is exactly zero, not for a small nonzero macd.
    zero_macd_score, _, _ = _score(monkeypatch, macd=0.0, macd_signal=-1.0, macd_hist=0.00007)
    nonzero_macd_score, _, _ = _score(monkeypatch, macd=0.01, macd_signal=-1.0, macd_hist=0.00007)
    assert zero_macd_score == 58     # +6 (crossover) + 2 (hist momentum triggers, threshold 0.00005)
    assert nonzero_macd_score == 56  # +6 (crossover) only (threshold 0.0005, 0.00007 doesn't clear it)


def test_macd_none_is_ignored(monkeypatch):
    assert _score(monkeypatch, macd=None, macd_signal=0.5)[0] == 50
    assert _score(monkeypatch, macd=0.5, macd_signal=None)[0] == 50


# ─────────────────────────────────────────────────────────────────────────
# Bollinger Bands
# ─────────────────────────────────────────────────────────────────────────

def test_bollinger_strong_below_lower_band_is_bullish(monkeypatch):
    score, _, _ = _score(monkeypatch, bollinger={"percent_b": -0.10})
    assert score == 60


def test_bollinger_near_lower_band_is_weakly_bullish(monkeypatch):
    score, _, _ = _score(monkeypatch, bollinger={"percent_b": 0.05})
    assert score == 54


def test_bollinger_strong_above_upper_band_is_bearish(monkeypatch):
    score, _, _ = _score(monkeypatch, bollinger={"percent_b": 1.10})
    assert score == 40


def test_bollinger_near_upper_band_is_weakly_bearish(monkeypatch):
    score, _, _ = _score(monkeypatch, bollinger={"percent_b": 0.95})
    assert score == 46


def test_bollinger_mid_band_has_no_effect(monkeypatch):
    assert _score(monkeypatch, bollinger={"percent_b": 0.5})[0] == 50


def test_bollinger_squeeze_message_is_added_to_long_signals_regardless_of_direction(monkeypatch):
    # A tight bandwidth (<5.0) appends a "kirilim olasiligi" message to
    # long_signals unconditionally - even though a squeeze is not itself a
    # bullish signal, it's coded as a long_signals entry with zero score
    # impact. Documented as-is, not moved to a neutral list.
    score, longs, _ = _score(monkeypatch, bollinger={"percent_b": 0.5, "bandwidth": 3.0})
    assert score == 50
    assert any("sikismasi" in s for s in longs)


def test_bollinger_none_is_ignored(monkeypatch):
    assert _score(monkeypatch, bollinger=None)[0] == 50


def test_bollinger_missing_percent_b_is_ignored(monkeypatch):
    assert _score(monkeypatch, bollinger={"percent_b": None})[0] == 50


# ─────────────────────────────────────────────────────────────────────────
# EMA Crossover
# ─────────────────────────────────────────────────────────────────────────

def test_ema_crossover_all_values(monkeypatch):
    assert _score(monkeypatch, ema_crossover="GOLDEN_CROSS")[0] == 60
    assert _score(monkeypatch, ema_crossover="DEATH_CROSS")[0] == 40
    assert _score(monkeypatch, ema_crossover="BULLISH")[0] == 52
    assert _score(monkeypatch, ema_crossover="BEARISH")[0] == 48
    assert _score(monkeypatch, ema_crossover="SIDEWAYS")[0] == 50  # unrecognized string -> no effect
    assert _score(monkeypatch, ema_crossover=None)[0] == 50


# ─────────────────────────────────────────────────────────────────────────
# Trend Strength
# ─────────────────────────────────────────────────────────────────────────

def test_trend_strength_all_zones(monkeypatch):
    assert _score(monkeypatch, trend_strength=10.0)[0] == 56   # > 8 -> +6
    assert _score(monkeypatch, trend_strength=5.0)[0] == 52    # > 3 -> +2
    assert _score(monkeypatch, trend_strength=-10.0)[0] == 44  # < -8 -> -6
    assert _score(monkeypatch, trend_strength=-5.0)[0] == 48   # < -3 -> -2
    assert _score(monkeypatch, trend_strength=0.0)[0] == 50


def test_trend_strength_boundaries_fall_to_weaker_or_no_tier(monkeypatch):
    # `> 8` and `> 3` are both strict, so exactly-on-boundary values land one
    # tier down (or in the dead zone) rather than the tier their magnitude
    # suggests.
    assert _score(monkeypatch, trend_strength=8.0)[0] == 52  # not > 8 -> falls to > 3 tier (+2)
    assert _score(monkeypatch, trend_strength=3.0)[0] == 50  # not > 3 -> no effect at all


# ─────────────────────────────────────────────────────────────────────────
# Volume ratio
# ─────────────────────────────────────────────────────────────────────────

def test_volume_ratio_high_with_no_prior_bull_or_bear_signals(monkeypatch):
    score, longs, _ = _score(monkeypatch, volume_ratio=2.5)
    assert score == 52  # bull_count/bear_count both 0 -> falls to the generic +2 branch
    assert any("ustunde" in s for s in longs)


def test_volume_ratio_high_with_two_prior_bull_signals_gets_bigger_bonus(monkeypatch):
    # RSI<20 and EMA GOLDEN_CROSS each set bull_count += 1 -> bull_count == 2
    # by the time the volume section runs (source order: potential price,
    # RSI, MACD, Bollinger, EMA, trend, THEN volume) -> the >=2 branch fires.
    score, longs, _ = _score(monkeypatch, rsi=15.0, ema_crossover="GOLDEN_CROSS", volume_ratio=2.5)
    assert score == 82  # 50 + 14 (RSI) + 10 (EMA) + 8 (volume, bull_count>=2 branch)
    assert any("cok guclu" in s for s in longs)


def test_volume_ratio_moderately_high(monkeypatch):
    assert _score(monkeypatch, volume_ratio=1.5)[0] == 52  # > 1.3, <= 2.0 -> +2


def test_volume_ratio_low(monkeypatch):
    score, _, shorts = _score(monkeypatch, volume_ratio=0.3)
    assert score == 47  # < 0.4 -> -3
    assert any("zayif" in s for s in shorts)


def test_volume_ratio_boundaries_are_neutral(monkeypatch):
    # Both comparisons are strict (`> 1.3`, `< 0.4`), so the exact boundary
    # values themselves have no effect.
    assert _score(monkeypatch, volume_ratio=1.3)[0] == 50
    assert _score(monkeypatch, volume_ratio=0.4)[0] == 50


# ─────────────────────────────────────────────────────────────────────────
# Williams %R
# ─────────────────────────────────────────────────────────────────────────

def test_williams_r_all_zones(monkeypatch):
    assert _score(monkeypatch, williams_r=-90.0)[0] == 58  # <= -80 -> +8
    assert _score(monkeypatch, williams_r=-70.0)[0] == 53  # <= -60 -> +3
    assert _score(monkeypatch, williams_r=-5.0)[0] == 42   # >= -10 -> -8
    assert _score(monkeypatch, williams_r=-20.0)[0] == 47  # >= -30 -> -3
    assert _score(monkeypatch, williams_r=-45.0)[0] == 50  # dead zone -> no effect


def test_williams_r_boundaries_are_inclusive(monkeypatch):
    assert _score(monkeypatch, williams_r=-80.0)[0] == 58  # <= is inclusive -> strong tier
    assert _score(monkeypatch, williams_r=-60.0)[0] == 53  # <= is inclusive -> weak tier
    assert _score(monkeypatch, williams_r=-10.0)[0] == 42  # >= is inclusive -> strong bear tier
    assert _score(monkeypatch, williams_r=-30.0)[0] == 47  # >= is inclusive -> weak bear tier


# ─────────────────────────────────────────────────────────────────────────
# CCI
# ─────────────────────────────────────────────────────────────────────────

def test_cci_all_zones(monkeypatch):
    assert _score(monkeypatch, cci=-200.0)[0] == 58  # < -150 -> +8
    assert _score(monkeypatch, cci=-120.0)[0] == 55  # < -100 -> +5
    assert _score(monkeypatch, cci=250.0)[0] == 42   # > 200 -> -8
    assert _score(monkeypatch, cci=150.0)[0] == 45   # > 100 -> -5
    assert _score(monkeypatch, cci=50.0)[0] == 50    # no zone matches -> no effect


def test_cci_zero_crossing_adds_message_but_no_score_change(monkeypatch):
    score, longs, _ = _score(monkeypatch, cci=0.0)
    assert score == 50
    assert any("sifir bölgesi" in s for s in longs)


def test_cci_neg150_and_200_fall_to_the_weaker_adjacent_tier(monkeypatch):
    # `cci < -150` / `cci > 200` are strict, so the exact boundary values
    # don't match their own "extreme" branch - they fall through to the
    # next elif (`< -100` / `> 100`, the weaker tier) instead of being a gap.
    assert _score(monkeypatch, cci=-150.0)[0] == 55  # weak bull tier (+5), not the +8 extreme tier
    assert _score(monkeypatch, cci=200.0)[0] == 45   # weak bear tier (-5), not the -8 extreme tier


def test_cci_exact_boundary_values_fall_into_true_gaps_with_no_effect(monkeypatch):
    # -100 and 100 are excluded by strict `<`/`>` on both adjacent branches
    # (`< -100` and the zero-crossing `-10 < cci < 10` don't reach them
    # either), and -10/10 are excluded by the zero-crossing check being
    # strict on both sides. Verified empirically against the real function
    # (session-neutralized) - these four values are true dead zones with no
    # effect at all, unlike -150/200 above.
    for boundary in (-100.0, 100.0, -10.0, 10.0):
        score, longs, shorts = _score(monkeypatch, cci=boundary)
        assert score == 50, f"cci={boundary} unexpectedly affected score"
        assert longs == [] and shorts == []


# ─────────────────────────────────────────────────────────────────────────
# VWAP
# ─────────────────────────────────────────────────────────────────────────

def test_vwap_price_above_is_bearish_but_does_not_count_toward_convergence(monkeypatch):
    # diff = (104-100)/100*100 = +4% -> > 3 -> -3, but note: no bear_count += 1 here,
    # unlike the symmetric bullish branch below. Asymmetric, documented as-is.
    score, _, shorts = _score(monkeypatch, current_price=104.0, vwap=100.0)
    assert score == 47
    assert any("ortalamaya donus riski" in s for s in shorts)


def test_vwap_price_below_is_bullish_and_does_count_toward_convergence(monkeypatch):
    score, longs, _ = _score(monkeypatch, current_price=96.0, vwap=100.0)
    assert score == 53  # diff = -4% -> < -3 -> +3, bull_count += 1
    assert any("destek bolgesi" in s for s in longs)


def test_vwap_boundary_exactly_3_percent_has_no_effect(monkeypatch):
    # Both comparisons are strict (`> 3`, `< -3`).
    assert _score(monkeypatch, current_price=103.0, vwap=100.0)[0] == 50
    assert _score(monkeypatch, current_price=97.0, vwap=100.0)[0] == 50


def test_vwap_skipped_when_current_price_is_zero(monkeypatch):
    assert _score(monkeypatch, current_price=0.0, potential_price=None, vwap=100.0)[0] == 50


# ─────────────────────────────────────────────────────────────────────────
# Rate of Change (ROC)
# ─────────────────────────────────────────────────────────────────────────

def test_roc_all_zones_never_affect_bull_or_bear_count(monkeypatch):
    # None of the four ROC branches increment bull_count/bear_count, so no
    # matter how extreme roc is, it can never by itself trigger the
    # convergence bonus later in the function.
    assert _score(monkeypatch, roc=20.0)[0] == 54    # > 15 -> +4
    assert _score(monkeypatch, roc=10.0)[0] == 52    # > 5 -> +2
    assert _score(monkeypatch, roc=-20.0)[0] == 46   # < -15 -> -4
    assert _score(monkeypatch, roc=-10.0)[0] == 48   # < -5 -> -2
    assert _score(monkeypatch, roc=0.0)[0] == 50


# ─────────────────────────────────────────────────────────────────────────
# Ichimoku Cloud
# ─────────────────────────────────────────────────────────────────────────

def test_ichimoku_cloud_signal(monkeypatch):
    assert _score(monkeypatch, ichimoku={"cloud_signal": "ABOVE_CLOUD"})[0] == 58
    assert _score(monkeypatch, ichimoku={"cloud_signal": "BELOW_CLOUD"})[0] == 42
    score, longs, _ = _score(monkeypatch, ichimoku={"cloud_signal": "INSIDE_CLOUD"})
    assert score == 50  # message only, no score change
    assert any("kararsizlik" in s for s in longs)


def test_ichimoku_tk_cross(monkeypatch):
    assert _score(monkeypatch, ichimoku={"tk_cross": "BULLISH"})[0] == 55
    assert _score(monkeypatch, ichimoku={"tk_cross": "BEARISH"})[0] == 45


def test_ichimoku_cloud_and_tk_cross_combine_independently(monkeypatch):
    # cloud_signal and tk_cross are checked in two separate if/elif blocks,
    # not mutually exclusive with each other - both can fire in one call.
    score, _, _ = _score(
        monkeypatch, ichimoku={"cloud_signal": "ABOVE_CLOUD", "tk_cross": "BULLISH"}
    )
    assert score == 63  # 50 + 8 + 5


# ─────────────────────────────────────────────────────────────────────────
# Divergence
# ─────────────────────────────────────────────────────────────────────────

def test_divergence_bullish_and_bearish(monkeypatch):
    score, longs, _ = _score(
        monkeypatch, divergence={"divergence": "BULLISH_DIVERGENCE", "description": "double bottom"}
    )
    assert score == 62
    assert any("double bottom" in s for s in longs)

    score, _, shorts = _score(
        monkeypatch, divergence={"divergence": "BEARISH_DIVERGENCE", "description": "double top"}
    )
    assert score == 38
    assert any("double top" in s for s in shorts)


def test_divergence_unrecognized_value_has_no_effect(monkeypatch):
    assert _score(monkeypatch, divergence={"divergence": "NONE", "description": ""})[0] == 50


# ─────────────────────────────────────────────────────────────────────────
# Balance status
# ─────────────────────────────────────────────────────────────────────────

def test_balance_status_positive_and_negative_are_asymmetric(monkeypatch):
    # +5 for Pozitif vs -6 for Negatif - not a symmetric +/-, documented as-is.
    assert _score(monkeypatch, balance_status="Pozitif")[0] == 55
    assert _score(monkeypatch, balance_status="Negatif")[0] == 44
    assert _score(monkeypatch, balance_status="Notr")[0] == 50
    assert _score(monkeypatch, balance_status="anything-else")[0] == 50


# ─────────────────────────────────────────────────────────────────────────
# Convergence ("yakinsama") bonus
# ─────────────────────────────────────────────────────────────────────────

def test_convergence_bonus_bullish_tiers(monkeypatch):
    # 3 independent bull_count += 1 signals: RSI<20, EMA GOLDEN_CROSS, Ichimoku ABOVE_CLOUD.
    score_3, _, _ = _score(
        monkeypatch, rsi=15.0, ema_crossover="GOLDEN_CROSS",
        ichimoku={"cloud_signal": "ABOVE_CLOUD"},
    )
    # base signals: +14 (RSI) +10 (EMA) +8 (Ichimoku) = +32, bull_count=3 -> +3 convergence
    assert score_3 == 50 + 32 + 3

    # 4 bull signals: add Divergence BULLISH.
    score_4, _, _ = _score(
        monkeypatch, rsi=15.0, ema_crossover="GOLDEN_CROSS",
        ichimoku={"cloud_signal": "ABOVE_CLOUD"},
        divergence={"divergence": "BULLISH_DIVERGENCE", "description": "d"},
    )
    # +32 + 12 (divergence) = +44, bull_count=4 -> +5 convergence
    assert score_4 == 50 + 44 + 5

    # 5 bull signals: add CCI < -150.
    score_5, _, _ = _score(
        monkeypatch, rsi=15.0, ema_crossover="GOLDEN_CROSS",
        ichimoku={"cloud_signal": "ABOVE_CLOUD"},
        divergence={"divergence": "BULLISH_DIVERGENCE", "description": "d"},
        cci=-200.0,
    )
    # +44 + 8 (cci) = +52 -> raw score 102, bull_count=5 -> +7 convergence -> 109,
    # THEN clamped to 100 (clamping happens once, after the convergence bonus,
    # right before the session-blend step).
    assert score_5 == 100


def test_convergence_bonus_bearish_tiers(monkeypatch):
    # 3 independent bear_count += 1 signals: RSI>80, EMA DEATH_CROSS, Ichimoku BELOW_CLOUD.
    score_3, _, _ = _score(
        monkeypatch, rsi=85.0, ema_crossover="DEATH_CROSS",
        ichimoku={"cloud_signal": "BELOW_CLOUD"},
    )
    # -14 -10 -8 = -32, bear_count=3 -> -3 convergence
    assert score_3 == 50 - 32 - 3

    # 4 bear signals: add Divergence BEARISH.
    score_4, _, _ = _score(
        monkeypatch, rsi=85.0, ema_crossover="DEATH_CROSS",
        ichimoku={"cloud_signal": "BELOW_CLOUD"},
        divergence={"divergence": "BEARISH_DIVERGENCE", "description": "d"},
    )
    # -32 - 12 (divergence) = -44, bear_count=4 -> -5 convergence
    assert score_4 == 50 - 44 - 5


# ─────────────────────────────────────────────────────────────────────────
# Session integration (compute_score's use of compute_session_score)
# ─────────────────────────────────────────────────────────────────────────

def test_compute_score_falls_back_to_base_score_if_session_step_raises(monkeypatch):
    """compute_score wraps the session call in a bare `except Exception`, so
    any failure there (bad data, a bug in session_analysis, whatever) is
    silently swallowed and the pre-session score is returned unchanged -
    the caller has no way to know the session step failed."""

    def raising_session_score(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("core.scoring.compute_session_score", raising_session_score)
    score, _, _ = compute_score(
        current_price=100.0, potential_price=None, volume_ratio=1.0,
        balance_status="Notr", rsi=15.0, macd=None, macd_signal=None,
    )
    assert score == 64  # base_score_clamped for rsi=15.0 alone (50+14), session step ignored


def test_compute_score_prepends_session_signals_only_during_overlap(monkeypatch):
    """When session_code == 'OVERLAP', session_signals are prepended to
    long_signals; for every other session code they're appended instead."""

    def fake_session_score(**kwargs):
        return {
            "session_adjusted_score": kwargs["base_score"],
            "session_signals": ["SESSION_MARKER"],
            "session_code": "OVERLAP",
        }

    monkeypatch.setattr("core.scoring.compute_session_score", fake_session_score)
    _, longs, _ = compute_score(
        current_price=80.0, potential_price=100.0, volume_ratio=1.0,
        balance_status="Notr", rsi=None, macd=None, macd_signal=None,
    )
    assert longs[0] == "SESSION_MARKER"  # prepended, not appended, because session_code == OVERLAP


def test_real_compute_session_score_output_depends_on_the_dt_argument():
    """compute_score() never passes `dt` through to compute_session_score(),
    so it always uses datetime.now() (see module docstring). This test calls
    the real, unpatched compute_session_score directly with two fixed `dt`
    values in different sessions to document, at its source, that identical
    technical inputs produce a different session_adjusted_score depending on
    the time of day - which is exactly what compute_score() is silently
    exposed to on every call."""
    tz = pytz.timezone("Europe/Istanbul")
    overlap_dt = tz.localize(datetime(2026, 1, 5, 16, 0, 0))   # 16:00 TR -> OVERLAP session
    asia_dt = tz.localize(datetime(2026, 1, 5, 5, 0, 0))       # 05:00 TR -> ASIA session

    overlap_result = real_compute_session_score(
        rsi=50.0, macd=0.0, macd_signal_val=0.0, macd_hist=0.0,
        volume_ratio=1.0, base_score=50, dt=overlap_dt,
    )
    asia_result = real_compute_session_score(
        rsi=50.0, macd=0.0, macd_signal_val=0.0, macd_hist=0.0,
        volume_ratio=1.0, base_score=50, dt=asia_dt,
    )
    assert overlap_result["session_code"] == "OVERLAP"
    assert asia_result["session_code"] == "ASIA"
    assert overlap_result["session_adjusted_score"] != asia_result["session_adjusted_score"]
