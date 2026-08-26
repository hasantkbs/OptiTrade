"""
Characterization tests for core/risk_manager.py (DynamicRiskManager, RiskLevels).

These document the CURRENT behavior exactly as implemented today,
including several numerical edge cases that look questionable (NaN/inf
inputs silently bypassing the "must be positive" guard, a stop-loss
placed above entry price going undetected, and a case where the rounded
`risk_reward_ratio` field can visually look like it meets the minimum
threshold while `is_valid` is actually False). Per project instruction,
none of this is fixed - it is preserved and documented here, with the
consolidated risk list in docs/architecture/migration-notes.md.
"""
import math

import pytest
from pydantic import ValidationError

from core.risk_manager import DynamicRiskManager, RiskLevels


# ─────────────────────────────────────────────────────────────────────────
# Normal scenarios — default multipliers
# ─────────────────────────────────────────────────────────────────────────

def test_default_multipliers_produce_expected_levels_and_invalidity():
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=100.0, atr=10.0)

    assert levels.entry_price == 100.0
    assert levels.atr == 10.0
    assert levels.stop_loss == 85.0        # 100 - 1.5*10
    assert levels.take_profit_1 == 120.0   # 100 + 2*10
    assert levels.take_profit_2 == 130.0   # 100 + 3*10
    assert levels.risk_per_unit == 15.0
    assert levels.reward_per_unit_tp1 == 20.0
    assert levels.risk_reward_ratio == 1.33  # round(20/15, 2)
    assert levels.is_valid is False           # 1.33 < default min_risk_reward_ratio (2.0)


def test_different_entry_price_and_atr_scale_proportionally():
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=50000.0, atr=500.0)  # e.g. BTC-scale numbers
    assert levels.stop_loss == 49250.0       # 50000 - 1.5*500
    assert levels.take_profit_1 == 51000.0   # 50000 + 2*500
    assert levels.take_profit_2 == 51500.0   # 50000 + 3*500
    assert levels.risk_reward_ratio == 1.33


# ─────────────────────────────────────────────────────────────────────────
# Normal scenarios — custom multipliers
# ─────────────────────────────────────────────────────────────────────────

def test_custom_multipliers_meeting_min_ratio_are_valid():
    rm = DynamicRiskManager(
        stop_loss_atr_multiplier=1.0,
        take_profit_1_atr_multiplier=2.0,
        min_risk_reward_ratio=2.0,
    )
    levels = rm.calculate(entry_price=100.0, atr=10.0)
    assert levels.risk_reward_ratio == 2.0
    assert levels.is_valid is True


def test_custom_min_risk_reward_ratio_threshold_is_configurable():
    rm = DynamicRiskManager(min_risk_reward_ratio=1.0)
    levels = rm.calculate(entry_price=100.0, atr=10.0)  # default multipliers -> ratio 1.33
    assert levels.is_valid is True  # 1.33 >= 1.0 now, same inputs as the default-False test above


def test_take_profit_2_multiplier_does_not_affect_is_valid():
    # is_valid is defined purely in terms of TP1's ratio - TP2 is informational only.
    rm_small_tp2 = DynamicRiskManager(take_profit_2_atr_multiplier=2.01)
    rm_huge_tp2 = DynamicRiskManager(take_profit_2_atr_multiplier=100.0)
    levels_small = rm_small_tp2.calculate(entry_price=100.0, atr=10.0)
    levels_huge = rm_huge_tp2.calculate(entry_price=100.0, atr=10.0)
    assert levels_small.is_valid == levels_huge.is_valid
    assert levels_small.risk_reward_ratio == levels_huge.risk_reward_ratio
    assert levels_small.take_profit_2 != levels_huge.take_profit_2  # only TP2 itself differs


# ─────────────────────────────────────────────────────────────────────────
# Boundary conditions
# ─────────────────────────────────────────────────────────────────────────

def test_is_valid_boundary_is_inclusive_at_exact_threshold():
    rm = DynamicRiskManager(
        stop_loss_atr_multiplier=1.0, take_profit_1_atr_multiplier=2.0,
        min_risk_reward_ratio=2.0,
    )
    levels = rm.calculate(entry_price=100.0, atr=10.0)  # ratio exactly 2.0
    assert levels.risk_reward_ratio == 2.0
    assert levels.is_valid is True  # `>=`, so exact equality passes


def test_is_valid_just_below_threshold_is_false():
    rm = DynamicRiskManager(
        stop_loss_atr_multiplier=1.0, take_profit_1_atr_multiplier=1.999,
        min_risk_reward_ratio=2.0,
    )
    levels = rm.calculate(entry_price=100.0, atr=10.0)
    assert levels.is_valid is False


def test_entry_price_or_atr_exactly_zero_raises():
    rm = DynamicRiskManager()
    with pytest.raises(ValueError):
        rm.calculate(entry_price=0.0, atr=10.0)
    with pytest.raises(ValueError):
        rm.calculate(entry_price=100.0, atr=0.0)


def test_entry_price_or_atr_just_above_zero_does_not_raise():
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=0.001, atr=0.001)
    assert levels.entry_price == 0.001


def test_entry_price_smaller_than_rounding_precision_displays_as_zero():
    # entry_price passes the `> 0` guard (it genuinely is positive), but the
    # output fields are rounded to 4 decimal places - a value below 0.00005
    # rounds to a displayed 0.0, indistinguishable in the output from the
    # entry_price=0.0 case that raises ValueError. No exception is raised
    # here; this is a valid call whose result just looks like the invalid
    # one once rounded.
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=1e-6, atr=1e-6)
    assert levels.entry_price == 0.0
    assert levels.atr == 0.0


# ─────────────────────────────────────────────────────────────────────────
# Invalid inputs
# ─────────────────────────────────────────────────────────────────────────

def test_negative_entry_price_raises_with_expected_message():
    rm = DynamicRiskManager()
    with pytest.raises(ValueError, match="entry_price ve atr pozitif olmalı"):
        rm.calculate(entry_price=-100.0, atr=10.0)


def test_negative_atr_raises_with_expected_message():
    rm = DynamicRiskManager()
    with pytest.raises(ValueError, match="entry_price ve atr pozitif olmalı"):
        rm.calculate(entry_price=100.0, atr=-10.0)


def test_both_entry_price_and_atr_invalid_raises_once():
    rm = DynamicRiskManager()
    with pytest.raises(ValueError):
        rm.calculate(entry_price=-1.0, atr=-1.0)


# ─────────────────────────────────────────────────────────────────────────
# Numerical edge cases
# ─────────────────────────────────────────────────────────────────────────

def test_nan_entry_price_bypasses_the_positivity_guard_silently():
    # `entry_price <= 0` is False for NaN (all comparisons with NaN except
    # != are False in IEEE 754), so `float('nan')` slips straight past the
    # "must be positive" check with no exception, and NaN propagates through
    # every computed field.
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=float("nan"), atr=10.0)
    assert math.isnan(levels.entry_price)
    assert math.isnan(levels.stop_loss)
    assert math.isnan(levels.take_profit_1)
    assert math.isnan(levels.risk_per_unit)
    # risk_per_unit (NaN) fails `> 0` (NaN comparisons are always False), so
    # the ratio falls back to the 0.0 default rather than becoming NaN itself.
    assert levels.risk_reward_ratio == 0.0
    assert levels.is_valid is False


def test_nan_atr_bypasses_the_positivity_guard_silently():
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=100.0, atr=float("nan"))
    assert math.isnan(levels.stop_loss)
    assert levels.risk_reward_ratio == 0.0
    assert levels.is_valid is False


def test_infinite_entry_price_bypasses_the_positivity_guard():
    # inf <= 0 is False, so this passes the guard too. stop_loss/TP1/TP2 all
    # become inf, but risk_per_unit/reward_per_unit_tp1 become NaN because
    # `inf - inf` is NaN in IEEE 754 - not an error, just a silently
    # nonsensical result with is_valid still resolving to False.
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=float("inf"), atr=10.0)
    assert math.isinf(levels.stop_loss)
    assert math.isinf(levels.take_profit_1)
    assert math.isnan(levels.risk_per_unit)
    assert math.isnan(levels.reward_per_unit_tp1)
    assert levels.risk_reward_ratio == 0.0
    assert levels.is_valid is False


def test_zero_stop_loss_multiplier_gives_zero_risk_per_unit_not_an_error():
    # stop_loss_atr_multiplier=0.0 -> stop_loss == entry_price exactly ->
    # risk_per_unit == 0.0 -> the `if risk_per_unit > 0` guard on the ratio
    # computation takes the `else 0.0` branch (not a ZeroDivisionError).
    rm = DynamicRiskManager(stop_loss_atr_multiplier=0.0)
    levels = rm.calculate(entry_price=100.0, atr=10.0)
    assert levels.stop_loss == 100.0
    assert levels.risk_per_unit == 0.0
    assert levels.risk_reward_ratio == 0.0
    assert levels.is_valid is False


def test_negative_stop_loss_multiplier_places_stop_loss_above_entry_undetected():
    # A negative stop_loss_atr_multiplier is not rejected by anything: the
    # resulting "stop-loss" price ends up ABOVE the entry price (nonsensical
    # for a long-only risk model) and risk_per_unit goes negative. Nothing
    # in DynamicRiskManager treats this as invalid input - it only affects
    # risk_reward_ratio via the same `risk_per_unit > 0` guard (negative
    # also fails it, so ratio falls back to 0.0), silently.
    rm = DynamicRiskManager(stop_loss_atr_multiplier=-1.0)
    levels = rm.calculate(entry_price=100.0, atr=10.0)
    assert levels.stop_loss == 110.0   # ABOVE entry_price (100) - not caught as invalid
    assert levels.risk_per_unit == -10.0
    assert levels.risk_reward_ratio == 0.0
    assert levels.is_valid is False


def test_oversized_atr_can_produce_a_negative_stop_loss_price_undetected():
    # An ATR larger than entry_price / stop_loss_atr_multiplier drives the
    # computed stop-loss price below zero - not a realistic price for any
    # real asset, but DynamicRiskManager has no sanity check on the sign of
    # the resulting price levels, only on the risk/reward ratio.
    rm = DynamicRiskManager()  # default 1.5x multiplier
    levels = rm.calculate(entry_price=100.0, atr=1000.0)
    assert levels.stop_loss == -1400.0  # 100 - 1.5*1000, a negative "price"
    assert levels.risk_per_unit == 1500.0  # still positive, so ratio computes normally
    assert levels.risk_reward_ratio == pytest.approx(1.33, abs=0.01)


def test_risk_reward_ratio_field_can_visually_meet_threshold_while_is_valid_is_false():
    # is_valid is computed by comparing the UNROUNDED ratio to
    # min_risk_reward_ratio, but the ratio returned in the RiskLevels object
    # is separately rounded to 2 decimals for display. A raw ratio of 1.996
    # rounds to a displayed 2.0 (Python's round-half-to-even on the nearest
    # representable float), which visually equals the default 2.0 minimum -
    # yet is_valid is False, because the comparison used the true, unrounded
    # 1.996. A reader of just the `risk_reward_ratio` field could easily
    # mistake this result for a passing setup.
    rm = DynamicRiskManager(
        stop_loss_atr_multiplier=1.0,
        take_profit_1_atr_multiplier=1.996,
        min_risk_reward_ratio=2.0,
    )
    levels = rm.calculate(entry_price=100.0, atr=10.0)
    assert levels.risk_reward_ratio == 2.0   # displayed value looks like it clears the bar
    assert levels.is_valid is False           # ... but it didn't, per the unrounded comparison


def test_rounding_applies_to_all_five_numeric_output_fields():
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=100.123456, atr=10.654321)
    for value in (
        levels.entry_price, levels.atr, levels.stop_loss,
        levels.take_profit_1, levels.take_profit_2,
        levels.risk_per_unit, levels.reward_per_unit_tp1,
    ):
        assert value == round(value, 4)
    assert levels.risk_reward_ratio == round(levels.risk_reward_ratio, 2)


# ─────────────────────────────────────────────────────────────────────────
# Risk calculation consistency / determinism
# ─────────────────────────────────────────────────────────────────────────

def test_calculate_is_deterministic_for_identical_inputs():
    rm = DynamicRiskManager()
    a = rm.calculate(entry_price=123.45, atr=6.78)
    b = rm.calculate(entry_price=123.45, atr=6.78)
    assert a == b  # pydantic BaseModel equality compares all fields
    assert a.model_dump() == b.model_dump()


def test_entry_price_minus_stop_loss_identity_holds_after_rounding():
    # risk_per_unit is computed from the UNROUNDED stop_loss (before its own
    # rounding), then independently rounded - so `entry - stop_loss` using
    # the ROUNDED output fields can differ very slightly from the ROUNDED
    # risk_per_unit field due to two separate roundings. Confirmed equal
    # here at 4 decimal places for a case with no rounding drift, but this
    # is not a mathematically guaranteed identity for all inputs.
    rm = DynamicRiskManager()
    levels = rm.calculate(entry_price=100.0, atr=10.0)
    assert round(levels.entry_price - levels.stop_loss, 4) == levels.risk_per_unit


def test_repeated_calculate_calls_do_not_share_mutable_state():
    rm = DynamicRiskManager()
    first = rm.calculate(entry_price=100.0, atr=10.0)
    second = rm.calculate(entry_price=200.0, atr=20.0)
    assert first.entry_price == 100.0  # unaffected by the later call
    assert second.entry_price == 200.0


# ─────────────────────────────────────────────────────────────────────────
# RiskLevels model — public contract
# ─────────────────────────────────────────────────────────────────────────

def test_risk_levels_requires_all_fields():
    with pytest.raises(ValidationError):
        RiskLevels()


def test_risk_levels_ignores_unknown_extra_fields():
    # pydantic v2's default model config is extra="ignore" - unrecognized
    # keyword arguments are silently dropped, not rejected and not stored.
    levels = RiskLevels(
        entry_price=100, atr=10, stop_loss=85, take_profit_1=120,
        take_profit_2=130, risk_per_unit=15, reward_per_unit_tp1=20,
        risk_reward_ratio=1.33, is_valid=False, made_up_field="surprise",
    )
    assert not hasattr(levels, "made_up_field")
    assert "made_up_field" not in levels.model_dump()


def test_risk_levels_coerces_int_inputs_to_float():
    levels = RiskLevels(
        entry_price=100, atr=10, stop_loss=85, take_profit_1=120,
        take_profit_2=130, risk_per_unit=15, reward_per_unit_tp1=20,
        risk_reward_ratio=2, is_valid=True,
    )
    assert isinstance(levels.entry_price, float) and levels.entry_price == 100.0
    assert isinstance(levels.risk_reward_ratio, float) and levels.risk_reward_ratio == 2.0
