"""Tests for ml_training/features/. Uses the real PostgreSQL/Redis-backed
Feature Store."""
from datetime import datetime, timedelta, timezone

import pytest

from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from ml_training.features import categories
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import FeatureCategory

_SYMBOL = "MLFEATTEST"


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_SYMBOL,))
    finally:
        fs.offline_store._pool.putconn(conn)
    for name in ["rsi_14", "pe_ratio", "news_sentiment_score", "future_risk_metric"]:
        fs.online_store._client.delete(f"feature_store:{_SYMBOL}:{name}")


# ─────────────────────────────────────────────────────────────────────────
# categories.py (pure)
# ─────────────────────────────────────────────────────────────────────────

def test_categorize_known_technical_feature():
    result = categories.categorize(["rsi_14"])
    assert result[FeatureCategory.TECHNICAL] == ["rsi_14"]


def test_categorize_known_fundamental_feature():
    result = categories.categorize(["pe_ratio"])
    assert result[FeatureCategory.FUNDAMENTAL] == ["pe_ratio"]


def test_categorize_known_news_feature():
    result = categories.categorize(["news_sentiment_score"])
    assert result[FeatureCategory.NEWS] == ["news_sentiment_score"]


def test_categorize_unknown_feature_falls_into_other():
    result = categories.categorize(["some_brand_new_feature"])
    assert result[FeatureCategory.OTHER] == ["some_brand_new_feature"]


def test_categorize_empty_list():
    assert categories.categorize([]) == {}


def test_categorize_omits_categories_with_no_matches():
    result = categories.categorize(["rsi_14"])
    assert FeatureCategory.NEWS not in result
    assert FeatureCategory.RISK not in result


def test_risk_regime_relative_strength_known_lists_are_currently_empty():
    # No engine under the frozen architecture writes these yet - any
    # matching feature name will still auto-categorize once one does.
    assert categories.KNOWN_CATEGORY_FEATURES[FeatureCategory.RISK] == []
    assert categories.KNOWN_CATEGORY_FEATURES[FeatureCategory.REGIME] == []
    assert categories.KNOWN_CATEGORY_FEATURES[FeatureCategory.RELATIVE_STRENGTH] == []


# ─────────────────────────────────────────────────────────────────────────
# extractor.py (real Feature Store)
# ─────────────────────────────────────────────────────────────────────────

def test_extract_returns_empty_vector_when_nothing_written(feature_store):
    vector = FeatureExtractor(feature_store=feature_store).extract(_SYMBOL)
    assert vector.values == {}
    assert vector.categories == {}


def test_extract_discovers_every_written_feature(feature_store):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name="rsi_14", value=55.0))
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name="pe_ratio", value=20.0))
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name="news_sentiment_score", value=0.4))

    vector = FeatureExtractor(feature_store=feature_store).extract(_SYMBOL)
    assert vector.values == {"rsi_14": 55.0, "pe_ratio": 20.0, "news_sentiment_score": 0.4}
    assert vector.categories[FeatureCategory.TECHNICAL] == ["rsi_14"]
    assert vector.categories[FeatureCategory.FUNDAMENTAL] == ["pe_ratio"]
    assert vector.categories[FeatureCategory.NEWS] == ["news_sentiment_score"]


def test_extract_future_feature_lands_in_other_category(feature_store):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name="future_risk_metric", value=0.1))
    vector = FeatureExtractor(feature_store=feature_store).extract(_SYMBOL)
    assert vector.categories[FeatureCategory.OTHER] == ["future_risk_metric"]


def test_extract_is_point_in_time_correct(feature_store):
    now = datetime.now(timezone.utc)
    feature_store.write_feature(
        FeatureValue(symbol=_SYMBOL, feature_name="rsi_14", value=40.0, event_timestamp=now - timedelta(days=10))
    )
    feature_store.write_feature(
        FeatureValue(symbol=_SYMBOL, feature_name="rsi_14", value=90.0, event_timestamp=now)
    )

    past_vector = FeatureExtractor(feature_store=feature_store).extract(_SYMBOL, as_of=now - timedelta(days=5))
    assert past_vector.values["rsi_14"] == 40.0  # must not see the future value written "today"


def test_extract_respect_ingestion_time_excludes_a_backfilled_value(feature_store):
    """A feature "backfilled" right now with a historical event_timestamp
    must not be visible to a historical as_of query once
    respect_ingestion_time=True is passed through - it wasn't actually
    known yet at that point in real time (production audit: point-in-time
    leakage). Default behavior (the other tests above) is unaffected."""
    now = datetime.now(timezone.utc)
    feature_store.write_feature(
        FeatureValue(symbol=_SYMBOL, feature_name="rsi_14", value=40.0, event_timestamp=now - timedelta(days=10))
    )

    past_vector = FeatureExtractor(feature_store=feature_store).extract(
        _SYMBOL, as_of=now - timedelta(days=5), respect_ingestion_time=True,
    )
    assert "rsi_14" not in past_vector.values


def test_extractor_defaults_to_real_feature_store():
    extractor = FeatureExtractor()
    assert isinstance(extractor.feature_store, FeatureStoreService)
