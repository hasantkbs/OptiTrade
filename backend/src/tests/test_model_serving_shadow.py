"""Tests for model_serving/shadow.py. Real PostgreSQL (Model Registry +
Continuous Learning's `learning_samples`) and real Feature Store - no
mocked production logic. Shadow votes must never be returned to any
caller - `run`/`submit` both return `None`; the only observable effect
is a new row in `learning_samples`."""
import time
from datetime import datetime, timezone

import numpy as np
import pytest

from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from learning.service import LearningService
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState, TaskType
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.registry.service import ModelRegistryService
from ml_training.training.service import create_trainer
from model_serving.inference import InferenceEngine
from model_serving.loader import ModelLoader
from model_serving.shadow import ShadowInferenceService

_FEATURE_NAMES = ["f0", "f1"]
_SYMBOL = "MSVCSHADOW"
_MODEL_ID_PREFIX = "shadow-test"


def _fitted_trainer_path(tmp_path):
    rng = np.random.RandomState(2)
    X = rng.rand(150, 2)
    y = np.where(X[:, 0] > 0.6, "BUY", np.where(X[:, 0] < 0.4, "SELL", "HOLD"))
    trainer = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
    trainer.fit(X, y)
    path = str(tmp_path / "model.joblib")
    trainer.save(path)
    return path


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    fs.write_feature(FeatureValue(symbol=_SYMBOL, feature_name="f0", value=0.9))
    fs.write_feature(FeatureValue(symbol=_SYMBOL, feature_name="f1", value=0.1))
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_SYMBOL,))
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
def shadow_model_id(registry_service, tmp_path):
    model_id = f"{_MODEL_ID_PREFIX}-model"
    artifact_path = _fitted_trainer_path(tmp_path)
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=_FEATURE_NAMES, label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
        engine_name=f"MLModel:{model_id}", engine_version="v1", artifact_path=artifact_path,
    )
    registry_service.register(entry)
    registry_service.start_shadow(model_id)
    return model_id


@pytest.fixture
def shadow_service(registry_service, feature_store, learning_service):
    loader = ModelLoader(registry_service=registry_service)
    inference_engine = InferenceEngine(feature_extractor=FeatureExtractor(feature_store=feature_store))
    return ShadowInferenceService(
        loader=loader, inference_engine=inference_engine, registry_service=registry_service,
        learning_service=learning_service,
    )


def test_run_with_no_shadow_models_is_a_silent_no_op(shadow_service):
    shadow_service.run(_SYMBOL)  # nothing registered - must not raise


def test_run_records_a_shadow_sample_for_each_shadow_model(shadow_service, shadow_model_id, learning_service):
    shadow_service.run(_SYMBOL)

    conn = learning_service.repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT source, engine_results FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
            rows = cur.fetchall()
    finally:
        learning_service.repository._pool.putconn(conn)

    assert len(rows) == 1
    assert rows[0][0] == "shadow"


def test_run_never_raises_when_a_shadow_model_fails_to_load(shadow_service, registry_service):
    # A registered SHADOW entry whose artifact_path doesn't exist must
    # be skipped (logged), never propagated - a single broken shadow
    # model must never break shadow evaluation for the others.
    model_id = f"{_MODEL_ID_PREFIX}-broken"
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=_FEATURE_NAMES, label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
        engine_name=f"MLModel:{model_id}", engine_version="v1", artifact_path="/tmp/does-not-exist-xyz.joblib",
    )
    registry_service.register(entry)
    registry_service.start_shadow(model_id)
    shadow_service.run(_SYMBOL)  # must not raise


def test_submit_is_fire_and_forget_and_eventually_records_a_sample(shadow_service, shadow_model_id, learning_service):
    shadow_service.submit(_SYMBOL)
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
    assert count == 1


def test_service_defaults_to_real_dependencies():
    svc = ShadowInferenceService()
    assert isinstance(svc.registry_service, ModelRegistryService)
    svc.shutdown()
