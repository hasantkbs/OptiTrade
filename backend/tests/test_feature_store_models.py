"""Tests for feature_store/models.py."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from feature_store.models import FeatureDefinition, FeatureRecord, FeatureValue, ValidationResult


def test_feature_value_defaults():
    fv = FeatureValue(symbol="BTC-USD", feature_name="rsi_14", value=55.5)
    assert fv.version == "v1"
    assert fv.event_timestamp.tzinfo is not None


def test_feature_value_explicit_fields():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fv = FeatureValue(symbol="BTC-USD", feature_name="rsi_14", value=55.5, version="v2", event_timestamp=ts)
    assert fv.version == "v2"
    assert fv.event_timestamp == ts


@pytest.mark.parametrize("field", ["symbol", "feature_name", "version"])
def test_feature_value_rejects_blank_fields(field):
    kwargs = dict(symbol="BTC-USD", feature_name="rsi_14", value=1.0, version="v1")
    kwargs[field] = "   "
    with pytest.raises(ValidationError):
        FeatureValue(**kwargs)


def test_feature_value_int_coerced_to_float():
    fv = FeatureValue(symbol="BTC-USD", feature_name="rsi_14", value=50)
    assert isinstance(fv.value, float)
    assert fv.value == 50.0


def test_feature_record_adds_ingestion_timestamp():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ingested = datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    record = FeatureRecord(
        symbol="BTC-USD", feature_name="rsi_14", value=55.5,
        event_timestamp=ts, ingestion_timestamp=ingested,
    )
    assert record.ingestion_timestamp == ingested
    assert record.event_timestamp == ts


def test_feature_record_requires_ingestion_timestamp():
    with pytest.raises(ValidationError):
        FeatureRecord(symbol="BTC-USD", feature_name="rsi_14", value=55.5)


def test_feature_definition_optional_bounds():
    d = FeatureDefinition(feature_name="rsi_14")
    assert d.min_value is None and d.max_value is None
    d2 = FeatureDefinition(feature_name="rsi_14", min_value=0.0, max_value=100.0)
    assert d2.min_value == 0.0 and d2.max_value == 100.0


def test_validation_result_defaults_to_empty_errors():
    result = ValidationResult(is_valid=True)
    assert result.errors == []
