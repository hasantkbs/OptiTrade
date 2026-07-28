"""Tests for model_serving/loader.py. Real PostgreSQL (ml_training's own
Model Registry) and real Redis (Model Cache), a real fitted trainer
persisted to a real temp file on disk - no mocked production logic."""
import os
import tempfile
from datetime import datetime, timezone

import numpy as np
import pytest

from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState, TaskType
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.registry.service import ModelRegistryService
from ml_training.training.service import create_trainer
from model_serving.cache import ModelMetadataCache
from model_serving.config import ModelServingConfig
from model_serving.exceptions import (
    ChecksumMismatchError,
    InvalidModelMetadataError,
    ModelVersionNotFoundError,
    NoActiveModelError,
)
from model_serving.loader import ModelLoader

_FEATURE_NAMES = ["f0", "f1"]
_MODEL_ID_PREFIX = "loader-test"


def _fitted_trainer():
    rng = np.random.RandomState(0)
    X = rng.rand(120, 2)
    y = np.where(X[:, 0] > 0.6, "BUY", np.where(X[:, 0] < 0.4, "SELL", "HOLD"))
    trainer = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
    trainer.fit(X, y)
    return trainer


def _entry(model_id: str, artifact_path: str, horizon_days: int = 1, feature_list=None,
           promotion_state=PromotionState.CANDIDATE) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=feature_list if feature_list is not None else _FEATURE_NAMES,
        label_name=LabelName.DIRECTION, horizon_days=horizon_days, training_date=datetime.now(timezone.utc),
        promotion_state=promotion_state, engine_name=f"MLModel:{model_id}", engine_version="v1",
        artifact_path=artifact_path,
    )


def _register_active(registry_service: ModelRegistryService, model_id: str, artifact_path: str, horizon_days: int = 1):
    """Registers a model and drives it through the real
    CANDIDATE -> SHADOW -> ACTIVE lifecycle - `ModelRegistryService.
    register` rejects registering directly as ACTIVE."""
    registry_service.register(_entry(model_id, artifact_path, horizon_days=horizon_days))
    registry_service.start_shadow(model_id)
    return registry_service.promote_to_active(model_id, approved_by="loader-test")


@pytest.fixture
def registry_service():
    repo = ModelRegistryRepository()
    svc = ModelRegistryService(repository=repo)
    yield svc
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_model_registry WHERE model_id LIKE %s", (f"{_MODEL_ID_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def cache():
    config = ModelServingConfig(redis_host="localhost", redis_port=6379, redis_db=15, cache_ttl_seconds=60)
    c = ModelMetadataCache(config=config)
    c._client.flushdb()
    yield c
    c._client.flushdb()


@pytest.fixture
def loader(registry_service, cache):
    return ModelLoader(registry_service=registry_service, cache=cache, config=ModelServingConfig(cache_ttl_seconds=60))


@pytest.fixture
def artifact_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "model.joblib")
        _fitted_trainer().save(path)
        yield path


def test_resolve_active_entry_raises_when_nothing_is_active(loader):
    with pytest.raises(NoActiveModelError):
        loader.resolve_active_entry(LabelName.DIRECTION, 999)


def test_resolve_active_entry_finds_a_real_registered_active_model(registry_service, loader, artifact_path):
    model_id = f"{_MODEL_ID_PREFIX}-resolve"
    _register_active(registry_service, model_id, artifact_path)
    resolved = loader.resolve_active_entry(LabelName.DIRECTION, 1)
    assert resolved.model_id == model_id


def test_resolve_active_entry_is_cached_on_second_call(registry_service, loader, cache, artifact_path):
    model_id = f"{_MODEL_ID_PREFIX}-cached"
    _register_active(registry_service, model_id, artifact_path)
    loader.resolve_active_entry(LabelName.DIRECTION, 1)
    assert cache.get_active_entry(LabelName.DIRECTION, 1) is not None
    # Second call must not need another registry hit - can't easily
    # assert "no DB call happened", so this asserts the cache actually
    # has the value the second call would read.
    assert loader.resolve_active_entry(LabelName.DIRECTION, 1).model_id == model_id


def test_load_returns_a_fitted_usable_trainer(registry_service, loader, artifact_path):
    model_id = f"{_MODEL_ID_PREFIX}-load"
    entry = _entry(model_id, artifact_path)
    registry_service.register(entry)

    loaded = loader.load(entry)
    assert loaded.trainer.is_fitted
    assert loaded.calibrated is None
    assert loaded.prediction_source is loaded.trainer
    assert len(loaded.checksum) == 64  # sha256 hex digest


def test_load_returns_the_same_in_process_instance_when_unchanged(registry_service, loader, artifact_path):
    model_id = f"{_MODEL_ID_PREFIX}-idempotent"
    entry = _entry(model_id, artifact_path)
    registry_service.register(entry)
    first = loader.load(entry)
    second = loader.load(entry)
    assert first is second


def test_load_rejects_empty_feature_list(registry_service, loader, artifact_path):
    model_id = f"{_MODEL_ID_PREFIX}-empty-features"
    entry = _entry(model_id, artifact_path, feature_list=[])
    registry_service.register(entry)
    with pytest.raises(InvalidModelMetadataError):
        loader.load(entry)


def test_load_rejects_missing_artifact_file(registry_service, loader):
    model_id = f"{_MODEL_ID_PREFIX}-missing-artifact"
    entry = _entry(model_id, "/tmp/definitely-does-not-exist-12345.joblib")
    registry_service.register(entry)
    with pytest.raises(InvalidModelMetadataError):
        loader.load(entry)


def test_load_version_override_loads_a_non_active_model(registry_service, loader, artifact_path):
    model_id = f"{_MODEL_ID_PREFIX}-candidate"
    entry = _entry(model_id, artifact_path, promotion_state=PromotionState.CANDIDATE)
    registry_service.register(entry)
    loaded = loader.load_version_override(model_id)
    assert loaded.entry.promotion_state == PromotionState.CANDIDATE


def test_load_version_override_raises_for_unknown_model(loader):
    with pytest.raises(ModelVersionNotFoundError):
        loader.load_version_override(f"{_MODEL_ID_PREFIX}-never-registered")


def test_warm_up_loads_every_active_model(registry_service, loader, artifact_path):
    _register_active(registry_service, f"{_MODEL_ID_PREFIX}-warm-a", artifact_path, horizon_days=1)
    _register_active(registry_service, f"{_MODEL_ID_PREFIX}-warm-b", artifact_path, horizon_days=3)
    loaded_count = loader.warm_up()
    assert loaded_count >= 2
    assert f"{_MODEL_ID_PREFIX}-warm-a" in loader.loaded_models()
    assert f"{_MODEL_ID_PREFIX}-warm-b" in loader.loaded_models()


def test_checksum_mismatch_is_detected_on_force_reload(registry_service, loader, artifact_path):
    model_id = f"{_MODEL_ID_PREFIX}-checksum"
    entry = _entry(model_id, artifact_path)
    registry_service.register(entry)
    loader.load(entry)

    loader.evict(model_id)
    with open(artifact_path, "ab") as handle:
        handle.write(b"tampered-bytes")

    with pytest.raises(ChecksumMismatchError):
        loader.force_reload(model_id)


def test_force_reload_succeeds_when_file_is_unchanged(registry_service, loader, artifact_path):
    model_id = f"{_MODEL_ID_PREFIX}-force-reload-clean"
    entry = _entry(model_id, artifact_path)
    registry_service.register(entry)
    loader.load(entry)
    loader.evict(model_id)
    reloaded = loader.force_reload(model_id)
    assert reloaded.entry.model_id == model_id


def test_service_defaults_to_real_dependencies():
    loader = ModelLoader()
    assert isinstance(loader.registry_service, ModelRegistryService)
