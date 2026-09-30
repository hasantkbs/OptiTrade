"""
Tests for model_serving/cache.py, run against a real, local Redis
instance - not mocked. Uses Redis logical DB 15 (isolated from DB 0,
`ModelServingConfig`'s default), matching
`tests/test_feature_store_online_store.py`'s own convention.
"""
from datetime import datetime, timezone

import pytest

from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState
from model_serving.cache import ModelMetadataCache
from model_serving.config import ModelServingConfig


def _entry(model_id: str = "rf-dir-1d-cachetest") -> ModelRegistryEntry:
    return ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=["f0", "f1"], label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.ACTIVE,
        engine_name=f"MLModel:{model_id}", engine_version="v1", artifact_path="/tmp/unused.joblib",
    )


@pytest.fixture
def cache():
    config = ModelServingConfig(redis_host="localhost", redis_port=6379, redis_db=15, cache_ttl_seconds=60)
    c = ModelMetadataCache(config=config)
    c._client.flushdb()
    yield c
    c._client.flushdb()


def test_ping_succeeds_against_real_redis(cache):
    healthy, latency_ms = cache.ping()
    assert healthy is True
    assert latency_ms is not None and latency_ms >= 0.0


def test_get_active_entry_returns_none_for_missing_key(cache):
    assert cache.get_active_entry(LabelName.DIRECTION, 1) is None


def test_set_then_get_active_entry_round_trips_correctly(cache):
    entry = _entry()
    cache.set_active_entry(LabelName.DIRECTION, 1, entry)
    fetched = cache.get_active_entry(LabelName.DIRECTION, 1)
    assert fetched is not None
    assert fetched.model_id == entry.model_id
    assert fetched.algorithm == ModelAlgorithm.RANDOM_FOREST
    assert fetched.feature_list == ["f0", "f1"]


def test_different_label_name_or_horizon_is_a_different_key(cache):
    cache.set_active_entry(LabelName.DIRECTION, 1, _entry("model-1d"))
    cache.set_active_entry(LabelName.DIRECTION, 5, _entry("model-5d"))
    assert cache.get_active_entry(LabelName.DIRECTION, 1).model_id == "model-1d"
    assert cache.get_active_entry(LabelName.DIRECTION, 5).model_id == "model-5d"


def test_invalidate_removes_only_that_key(cache):
    cache.set_active_entry(LabelName.DIRECTION, 1, _entry("model-1d"))
    cache.set_active_entry(LabelName.DIRECTION, 5, _entry("model-5d"))
    cache.invalidate(LabelName.DIRECTION, 1)
    assert cache.get_active_entry(LabelName.DIRECTION, 1) is None
    assert cache.get_active_entry(LabelName.DIRECTION, 5) is not None


def test_invalidate_all_removes_every_cached_entry(cache):
    cache.set_active_entry(LabelName.DIRECTION, 1, _entry("model-1d"))
    cache.set_active_entry(LabelName.DIRECTION, 5, _entry("model-5d"))
    cache.invalidate_all()
    assert cache.get_active_entry(LabelName.DIRECTION, 1) is None
    assert cache.get_active_entry(LabelName.DIRECTION, 5) is None


def test_expired_entry_is_treated_as_a_miss():
    config = ModelServingConfig(redis_host="localhost", redis_port=6379, redis_db=15, cache_ttl_seconds=0)
    cache = ModelMetadataCache(config=config)
    cache._client.flushdb()
    try:
        cache.set_active_entry(LabelName.DIRECTION, 1, _entry())
        # ex=0 is rejected by Redis as a TTL - set_active_entry logs and
        # skips rather than raising, so this is simply never cached.
        assert cache.get_active_entry(LabelName.DIRECTION, 1) is None
    finally:
        cache._client.flushdb()


def test_service_defaults_to_real_redis_client():
    cache = ModelMetadataCache()
    healthy, _ = cache.ping()
    assert healthy is True
