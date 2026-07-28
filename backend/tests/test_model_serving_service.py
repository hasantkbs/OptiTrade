"""End-to-end tests for model_serving/service.py:PredictionService -
real PostgreSQL (Model Registry, Continuous Learning), real Redis
(Model Cache), a real fitted trainer, and real Feature Store data. This
is the same integration surface `main.py`'s `/quant/predict` and
`pipeline.service.PipelineService` both depend on."""
import os
import time
from datetime import datetime, timezone

import numpy as np
import pytest

from decision_engine.models import Prediction
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from learning.service import LearningService
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState, TaskType
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.registry.service import ModelRegistryService
from ml_training.training.service import create_trainer
from model_serving.cache import ModelMetadataCache
from model_serving.config import ModelServingConfig
from model_serving.exceptions import NoActiveModelError
from model_serving.health import HealthMonitor
from model_serving.inference import InferenceEngine
from model_serving.loader import ModelLoader
from model_serving.rollback import RollbackRepository, RollbackService
from model_serving.service import PredictionService
from model_serving.shadow import ShadowInferenceService

_FEATURE_NAMES = ["f0", "f1"]
_SYMBOL = "MSVCSERVICE"
_MODEL_ID_PREFIX = "svc-test"


def _fitted_trainer():
    rng = np.random.RandomState(3)
    X = rng.rand(150, 2)
    y = np.where(X[:, 0] > 0.6, "BUY", np.where(X[:, 0] < 0.4, "SELL", "HOLD"))
    trainer = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
    trainer.fit(X, y)
    return trainer


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    fs.write_feature(FeatureValue(symbol=_SYMBOL, feature_name="f0", value=0.9))
    fs.write_feature(FeatureValue(symbol=_SYMBOL, feature_name="f1", value=0.1))
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM feature_store_records WHERE symbol = %s OR symbol LIKE %s",
                (_SYMBOL, f"{_MODEL_ID_PREFIX}%"),
            )
    finally:
        fs.offline_store._pool.putconn(conn)
    fs.online_store._client.delete(f"feature_store:{_SYMBOL}:f0")
    fs.online_store._client.delete(f"feature_store:{_SYMBOL}:f1")


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
def rollback_repository():
    repo = RollbackRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM model_serving_rollback_overrides WHERE model_id LIKE %s", (f"{_MODEL_ID_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def learning_service():
    svc = LearningService()
    yield svc
    conn = svc.repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
    finally:
        svc.repository._pool.putconn(conn)


@pytest.fixture
def active_model(registry_service, tmp_path):
    model_id = f"{_MODEL_ID_PREFIX}-active"
    artifact_path = str(tmp_path / "active.joblib")
    _fitted_trainer().save(artifact_path)
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=_FEATURE_NAMES, label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
        engine_name=f"MLModel:{model_id}", engine_version="v1", artifact_path=artifact_path,
    )
    registry_service.register(entry)
    registry_service.start_shadow(model_id)
    return registry_service.promote_to_active(model_id, approved_by="svc-test")


@pytest.fixture
def service(registry_service, rollback_repository, feature_store, learning_service):
    config = ModelServingConfig(redis_host="localhost", redis_port=6379, redis_db=15, cache_ttl_seconds=60)
    cache = ModelMetadataCache(config=config)
    cache._client.flushdb()
    loader = ModelLoader(registry_service=registry_service, cache=cache, config=config)
    inference_engine = InferenceEngine(feature_extractor=FeatureExtractor(feature_store=feature_store), config=config)
    shadow_service = ShadowInferenceService(
        loader=loader, inference_engine=inference_engine, registry_service=registry_service,
        learning_service=learning_service, config=config,
    )
    rollback_service = RollbackService(repository=rollback_repository, registry_service=registry_service)
    health_monitor = HealthMonitor(loader=loader, cache=cache, config=config)
    svc = PredictionService(
        loader=loader, inference_engine=inference_engine, shadow_service=shadow_service,
        rollback_service=rollback_service, health_monitor=health_monitor, feature_store=feature_store, config=config,
    )
    yield svc
    cache._client.flushdb()
    shadow_service.shutdown()
    inference_engine.shutdown()


def test_predict_raises_when_nothing_is_active(service):
    with pytest.raises(NoActiveModelError):
        service.predict(_SYMBOL, label_name=LabelName.DIRECTION, horizon_days=999)


def test_predict_returns_a_full_result_for_an_active_model(service, active_model):
    result = service.predict(_SYMBOL, label_name=LabelName.DIRECTION, horizon_days=1)
    assert result.symbol == _SYMBOL
    assert result.vote.prediction in {Prediction.BUY, Prediction.HOLD, Prediction.SELL}
    assert result.metadata.model_id == active_model.model_id
    assert result.metadata.promotion_state == PromotionState.ACTIVE
    assert result.metadata.is_calibrated is False
    assert result.metadata.version_override_used is False
    assert len(result.metadata.checksum) == 64


def test_predict_with_model_id_override_bypasses_active_resolution(service, registry_service, tmp_path):
    candidate_id = f"{_MODEL_ID_PREFIX}-override-candidate"
    artifact_path = str(tmp_path / "candidate.joblib")
    _fitted_trainer().save(artifact_path)
    entry = ModelRegistryEntry(
        model_id=candidate_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=_FEATURE_NAMES, label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
        engine_name=f"MLModel:{candidate_id}", engine_version="v1", artifact_path=artifact_path,
    )
    registry_service.register(entry)

    result = service.predict(_SYMBOL, model_id_override=candidate_id)
    assert result.metadata.model_id == candidate_id
    assert result.metadata.version_override_used is True
    assert result.metadata.promotion_state == PromotionState.CANDIDATE


def test_predict_async_matches_sync_result_shape(service, active_model):
    import asyncio
    result = asyncio.run(service.predict_async(_SYMBOL, label_name=LabelName.DIRECTION, horizon_days=1))
    assert result.metadata.model_id == active_model.model_id


def test_predict_populates_explanation_inputs_from_feature_store(service, active_model, feature_store):
    feature_store.write_feature(
        FeatureValue(symbol=active_model.model_id, feature_name="shap_importance:f0", value=0.7)
    )
    feature_store.write_feature(
        FeatureValue(symbol=active_model.model_id, feature_name="shap_importance:f1", value=0.3)
    )
    result = service.predict(_SYMBOL, label_name=LabelName.DIRECTION, horizon_days=1)
    assert result.explanation_inputs == {"shap_importance:f0": 0.7, "shap_importance:f1": 0.3}


def test_get_active_engines_includes_the_registered_active_model(service, active_model):
    engines = service.get_active_engines()
    names = {engine.engine_name for engine in engines}
    assert active_model.engine_name in names


def test_get_active_engines_is_empty_when_nothing_is_active(service):
    assert service.get_active_engines() == []


def test_rollback_changes_which_model_get_active_engines_serves(service, registry_service, active_model, tmp_path):
    rollback_target_id = f"{_MODEL_ID_PREFIX}-rollback-target"
    artifact_path = str(tmp_path / "rollback.joblib")
    _fitted_trainer().save(artifact_path)
    entry = ModelRegistryEntry(
        model_id=rollback_target_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=_FEATURE_NAMES, label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
        engine_name=f"MLModel:{rollback_target_id}", engine_version="v1", artifact_path=artifact_path,
    )
    registry_service.register(entry)

    service.rollback_to(LabelName.DIRECTION, 1, rollback_target_id, rolled_back_by="svc-test")
    engines = service.get_active_engines()
    names = {engine.engine_name for engine in engines}
    assert f"MLModel:{rollback_target_id}" in names
    assert active_model.engine_name not in names

    # ml_training.registry itself is untouched - the previously-ACTIVE
    # model is neither archived nor deleted.
    assert registry_service.get(active_model.model_id).promotion_state == PromotionState.ACTIVE

    service.clear_rollback(LabelName.DIRECTION, 1)
    engines_after_clear = {engine.engine_name for engine in service.get_active_engines()}
    assert active_model.engine_name in engines_after_clear


def test_health_report_reflects_latency_after_a_prediction(service, active_model):
    service.predict(_SYMBOL, label_name=LabelName.DIRECTION, horizon_days=1)
    report = service.health_report()
    assert report.cache.healthy is True
    assert report.inference_latency.sample_count >= 1
    assert any(status.model_id == active_model.model_id for status in report.models)


def test_predict_submits_shadow_inference_for_shadow_models(service, registry_service, active_model, learning_service, tmp_path):
    shadow_id = f"{_MODEL_ID_PREFIX}-shadow"
    artifact_path = str(tmp_path / "shadow.joblib")
    _fitted_trainer().save(artifact_path)
    entry = ModelRegistryEntry(
        model_id=shadow_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=_FEATURE_NAMES, label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
        engine_name=f"MLModel:{shadow_id}", engine_version="v1", artifact_path=artifact_path,
    )
    registry_service.register(entry)
    registry_service.start_shadow(shadow_id)

    service.predict(_SYMBOL, label_name=LabelName.DIRECTION, horizon_days=1)

    count = 0
    for _ in range(50):
        conn = learning_service.repository._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
                count = cur.fetchone()[0]
        finally:
            learning_service.repository._pool.putconn(conn)
        if count >= 1:
            break
        time.sleep(0.05)
    assert count >= 1


def test_predict_with_override_does_not_submit_shadow_inference(service, registry_service, tmp_path, learning_service):
    candidate_id = f"{_MODEL_ID_PREFIX}-no-shadow-trigger"
    artifact_path = str(tmp_path / "no_shadow.joblib")
    _fitted_trainer().save(artifact_path)
    entry = ModelRegistryEntry(
        model_id=candidate_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=_FEATURE_NAMES, label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
        engine_name=f"MLModel:{candidate_id}", engine_version="v1", artifact_path=artifact_path,
    )
    registry_service.register(entry)

    service.predict(_SYMBOL, model_id_override=candidate_id)
    time.sleep(0.2)

    conn = learning_service.repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
            count = cur.fetchone()[0]
    finally:
        learning_service.repository._pool.putconn(conn)
    assert count == 0


def test_service_defaults_to_real_dependencies():
    svc = PredictionService()
    assert isinstance(svc.loader, ModelLoader)
    assert isinstance(svc.inference_engine, InferenceEngine)
    svc.shadow_service.shutdown()
    svc.inference_engine.shutdown()
