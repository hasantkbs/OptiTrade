"""Tests for feature_store/validation.py."""
import math

from feature_store.models import FeatureDefinition, FeatureValue
from feature_store.validation import FeatureValidator


def _fv(value):
    return FeatureValue(symbol="BTC-USD", feature_name="rsi_14", value=value)


def test_valid_numeric_value_passes():
    result = FeatureValidator().validate(_fv(55.5))
    assert result.is_valid is True
    assert result.errors == []


def test_nan_is_rejected():
    result = FeatureValidator().validate(_fv(math.nan))
    assert result.is_valid is False
    assert any("NaN" in e for e in result.errors)


def test_infinite_is_rejected():
    result = FeatureValidator().validate(_fv(math.inf))
    assert result.is_valid is False
    assert any("infinite" in e for e in result.errors)

    result_neg = FeatureValidator().validate(_fv(-math.inf))
    assert result_neg.is_valid is False


def test_bool_value_is_coerced_to_float_by_feature_value_itself():
    # FeatureValue.value is a pydantic `float` field, so pydantic already
    # coerces a bool to a float (True -> 1.0) at construction time, before
    # FeatureValidator ever sees it - the validator has nothing left to
    # reject here, this documents where that guarantee actually lives.
    fv = _fv(True)
    assert fv.value == 1.0
    assert isinstance(fv.value, float)
    result = FeatureValidator().validate(fv)
    assert result.is_valid is True


def test_unregistered_feature_name_has_no_range_check():
    result = FeatureValidator().validate(_fv(999999.0))
    assert result.is_valid is True


def test_registered_range_check_rejects_below_minimum():
    validator = FeatureValidator({"rsi_14": FeatureDefinition(feature_name="rsi_14", min_value=0.0, max_value=100.0)})
    result = validator.validate(_fv(-5.0))
    assert result.is_valid is False
    assert any("below minimum" in e for e in result.errors)


def test_registered_range_check_rejects_above_maximum():
    validator = FeatureValidator({"rsi_14": FeatureDefinition(feature_name="rsi_14", min_value=0.0, max_value=100.0)})
    result = validator.validate(_fv(150.0))
    assert result.is_valid is False
    assert any("above maximum" in e for e in result.errors)


def test_registered_range_check_accepts_within_bounds():
    validator = FeatureValidator({"rsi_14": FeatureDefinition(feature_name="rsi_14", min_value=0.0, max_value=100.0)})
    result = validator.validate(_fv(50.0))
    assert result.is_valid is True


def test_register_adds_a_definition_after_construction():
    validator = FeatureValidator()
    assert validator.validate(_fv(150.0)).is_valid is True  # no bounds yet
    validator.register(FeatureDefinition(feature_name="rsi_14", min_value=0.0, max_value=100.0))
    assert validator.validate(_fv(150.0)).is_valid is False  # now bounded
