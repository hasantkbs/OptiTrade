"""Tests for model_serving/health.py. Real Redis for cache_health();
`ModelLoader`'s in-process bookkeeping is populated directly (a
`LoadedModel` needs a real fitted trainer to construct meaningfully,
which `test_model_serving_service.py` already exercises end-to-end -
this file focuses purely on health.py's own aggregation/statistics
logic, which only reads `loader.loaded_models()`/`last_load_error()`/
`loading_failure_count`, so a lightweight fake trainer object is enough)."""
from datetime import datetime, timedelta, timezone

import pytest

from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState
from model_serving.cache import ModelMetadataCache
from model_serving.config import ModelServingConfig
from model_serving.health import HealthMonitor
from model_serving.loader import LoadedModel, ModelLoader


def _entry(model_id: str) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=["f0"], label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.ACTIVE,
        engine_name=f"MLModel:{model_id}", engine_version="v1", artifact_path=f"/tmp/{model_id}.joblib",
    )


@pytest.fixture
def cache():
    config = ModelServingConfig(redis_host="localhost", redis_port=6379, redis_db=15, cache_ttl_seconds=60)
    c = ModelMetadataCache(config=config)
    c._client.flushdb()
    yield c
    c._client.flushdb()


@pytest.fixture
def loader(cache):
    config = ModelServingConfig(cache_ttl_seconds=60, latency_history_size=5)
    return ModelLoader(cache=cache, config=config)


@pytest.fixture
def monitor(loader, cache):
    return HealthMonitor(loader=loader, cache=cache, config=ModelServingConfig(cache_ttl_seconds=60, latency_history_size=5))


def test_latency_stats_empty_by_default(monitor):
    stats = monitor.latency_stats()
    assert stats.sample_count == 0
    assert stats.avg_ms == 0.0


def test_latency_stats_computes_avg_p50_p95(monitor):
    for value in [10.0, 20.0, 30.0, 40.0, 50.0]:
        monitor.record_latency(value)
    stats = monitor.latency_stats()
    assert stats.sample_count == 5
    assert stats.avg_ms == pytest.approx(30.0)
    assert stats.p50_ms == pytest.approx(30.0)
    assert stats.p95_ms == pytest.approx(50.0)


def test_latency_history_is_bounded_by_config(monitor):
    for value in range(20):
        monitor.record_latency(float(value))
    assert monitor.latency_stats().sample_count == 5  # latency_history_size=5


def test_cache_health_reports_healthy_for_real_redis(monitor):
    status = monitor.cache_health()
    assert status.healthy is True
    assert status.latency_ms is not None
    assert status.error is None


def test_model_health_reports_nothing_when_no_model_loaded(monitor):
    assert monitor.model_health() == []


def test_model_health_reports_a_loaded_and_fresh_model(loader, monitor):
    entry = _entry("health-test-fresh")
    loader._loaded[entry.model_id] = LoadedModel(
        entry=entry, trainer=object(), calibrated=None, checksum="abc123", loaded_at=datetime.now(timezone.utc),
    )
    statuses = monitor.model_health()
    assert len(statuses) == 1
    assert statuses[0].model_id == "health-test-fresh"
    assert statuses[0].loaded is True
    assert statuses[0].stale is False
    assert statuses[0].last_error is None


def test_model_health_reports_a_stale_model(loader, monitor):
    entry = _entry("health-test-stale")
    old_timestamp = datetime.now(timezone.utc) - timedelta(seconds=120)
    loader._loaded[entry.model_id] = LoadedModel(
        entry=entry, trainer=object(), calibrated=None, checksum="abc123", loaded_at=old_timestamp,
    )
    statuses = monitor.model_health()
    assert statuses[0].stale is True


def test_model_health_surfaces_the_last_load_error(loader, monitor):
    loader._last_load_error["health-test-error"] = "InvalidModelMetadataError: boom"
    entry = _entry("health-test-error")
    loader._loaded[entry.model_id] = LoadedModel(
        entry=entry, trainer=object(), calibrated=None, checksum="abc123", loaded_at=datetime.now(timezone.utc),
    )
    statuses = monitor.model_health()
    assert statuses[0].last_error == "InvalidModelMetadataError: boom"


def test_report_aggregates_everything(loader, monitor):
    monitor.record_latency(15.0)
    loader.loading_failure_count = 2
    report = monitor.report()
    assert report.cache.healthy is True
    assert report.inference_latency.sample_count == 1
    assert report.loading_failure_count == 2
    assert report.models == []
