"""Tests for ml_training/shadow/. Real Feature Store (PostgreSQL/Redis),
real Continuous Learning persistence, an isolated `EngineRegistry`
instance (never `engine_registry.default_registry`, per that module's
own test-isolation guidance)."""
import os
import tempfile
from datetime import datetime, timezone

import numpy as np
import pytest

from decision_engine.models import Prediction
from engine_registry.registry import EngineRegistry
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from learning.scheduler import LearningCycleResult
from learning.service import LearningService
from ml_training.config import MLTrainingConfig
from ml_training.exceptions import InvalidPromotionError
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState, TaskType
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.registry.service import ModelRegistryService
from ml_training.shadow.adapter import MLModelVotingEngineAdapter
from ml_training.shadow.service import MLShadowService
from ml_training.training.service import create_trainer
from research_lab.shadow.service import ShadowEvaluationService

_FEATURE_NAMES = ["f0", "f1"]
_SYMBOL = "MLSHADOWTEST"
_MODEL_ID_PREFIX = "shadow-svc-test"


def _fitted_direction_trainer():
    rng = np.random.RandomState(0)
    X = rng.rand(200, 2)
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
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_SYMBOL,))
    finally:
        fs.offline_store._pool.putconn(conn)
    fs.online_store._client.delete(f"feature_store:{_SYMBOL}:f0")
    fs.online_store._client.delete(f"feature_store:{_SYMBOL}:f1")


# ─────────────────────────────────────────────────────────────────────────
# adapter.py
# ─────────────────────────────────────────────────────────────────────────

def test_adapter_rejects_a_trainer_that_is_not_fitted_classification():
    unfitted = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES)
    with pytest.raises(ValueError):
        MLModelVotingEngineAdapter("model-x", "v1", unfitted, _FEATURE_NAMES)


def test_adapter_vote_produces_a_valid_engine_vote(feature_store):
    trainer = _fitted_direction_trainer()
    adapter = MLModelVotingEngineAdapter(
        "adapter-test", "v1", trainer, _FEATURE_NAMES,
        feature_extractor=FeatureExtractor(feature_store=feature_store),
        config=MLTrainingConfig(expected_return_scale_pct=10.0, default_expected_volatility_pct=15.0),
    )
    assert adapter.engine_name == "MLModel:adapter-test"

    vote = adapter.vote(_SYMBOL)
    assert vote.engine_name == "MLModel:adapter-test"
    assert vote.engine_version == "v1"
    assert vote.prediction in {Prediction.BUY, Prediction.HOLD, Prediction.SELL}
    assert 0.0 <= vote.confidence <= 1.0
    assert vote.volatility == 15.0
    assert -10.0 <= vote.expected_return <= 10.0
    assert vote.evidence


def test_adapter_satisfies_voting_engine_protocol(feature_store):
    from decision_engine.interfaces import VotingEngineProtocol

    trainer = _fitted_direction_trainer()
    adapter = MLModelVotingEngineAdapter(
        "adapter-protocol-test", "v1", trainer, _FEATURE_NAMES,
        feature_extractor=FeatureExtractor(feature_store=feature_store),
    )
    assert isinstance(adapter, VotingEngineProtocol)


# ─────────────────────────────────────────────────────────────────────────
# service.py
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def registry_repository():
    repo = ModelRegistryRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_model_registry WHERE model_id LIKE %s", (f"{_MODEL_ID_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def registry_service(registry_repository):
    return ModelRegistryService(repository=registry_repository)


@pytest.fixture
def isolated_engine_registry():
    return EngineRegistry()


@pytest.fixture
def registered_model(registry_service):
    """A CANDIDATE registry entry pointing at a real, saved trainer
    artifact (written straight into the OS temp dir, not a
    `TemporaryDirectory` context manager, so it survives for the whole
    test rather than being deleted as soon as the fixture body returns)."""
    trainer = _fitted_direction_trainer()
    model_id = f"{_MODEL_ID_PREFIX}-{os.getpid()}-{id(trainer)}"
    artifact_path = os.path.join(tempfile.gettempdir(), f"{model_id}.joblib")
    trainer.save(artifact_path)

    entry = registry_service.register(
        ModelRegistryEntry(
            model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
            hyperparameters=trainer.hyperparameters, metrics=None, feature_list=_FEATURE_NAMES,
            label_name=LabelName.DIRECTION, horizon_days=5, training_date=datetime.now(timezone.utc),
            promotion_state=PromotionState.CANDIDATE, engine_name=f"MLModel:{model_id}", engine_version="v1",
            artifact_path=artifact_path,
        )
    )
    yield entry
    if os.path.exists(artifact_path):
        os.remove(artifact_path)


def test_deploy_shadow_registers_adapter_and_transitions_to_shadow(
    registry_service, isolated_engine_registry, registered_model,
):
    shadow_service = MLShadowService(registry_service=registry_service, engine_registry=isolated_engine_registry)
    adapter = shadow_service.deploy_shadow(registered_model.model_id)

    assert adapter.engine_name == registered_model.engine_name
    assert isolated_engine_registry.get(adapter.engine_name, adapter.engine_version) is adapter

    entry = registry_service.get(registered_model.model_id)
    assert entry.promotion_state == PromotionState.SHADOW


def test_deploy_shadow_raises_for_unknown_model(registry_service, isolated_engine_registry):
    shadow_service = MLShadowService(registry_service=registry_service, engine_registry=isolated_engine_registry)
    with pytest.raises(InvalidPromotionError):
        shadow_service.deploy_shadow(f"{_MODEL_ID_PREFIX}-never-registered")


def test_run_shadow_pass_requires_shadow_state(registry_service, isolated_engine_registry, registered_model):
    shadow_service = MLShadowService(registry_service=registry_service, engine_registry=isolated_engine_registry)
    with pytest.raises(InvalidPromotionError):
        shadow_service.run_shadow_pass(registered_model.model_id, [_SYMBOL])


def test_run_shadow_pass_records_a_learning_sample(
    registry_service, isolated_engine_registry, registered_model, feature_store,
):
    shadow_service = MLShadowService(
        registry_service=registry_service, engine_registry=isolated_engine_registry,
        shadow_evaluation_service=ShadowEvaluationService(),
    )
    shadow_service.deploy_shadow(registered_model.model_id)

    # Swap in a feature_extractor pointed at the test's Feature Store
    # for the just-registered adapter, then re-register it.
    adapter = isolated_engine_registry.get(registered_model.engine_name, "v1")
    adapter.feature_extractor = FeatureExtractor(feature_store=feature_store)

    try:
        samples = shadow_service.run_shadow_pass(registered_model.model_id, [_SYMBOL])
        assert len(samples) == 1
        assert samples[0].symbol == _SYMBOL
        assert samples[0].engine_results[0].engine_name == registered_model.engine_name
    finally:
        learning_service = LearningService()
        conn = learning_service.repository._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
        finally:
            learning_service.repository._pool.putconn(conn)


def test_run_learning_cycle_delegates_to_learning_service(registry_service, isolated_engine_registry):
    shadow_service = MLShadowService(registry_service=registry_service, engine_registry=isolated_engine_registry)
    result = shadow_service.run_learning_cycle()
    assert isinstance(result, LearningCycleResult)


def test_service_defaults_to_real_dependencies():
    svc = MLShadowService()
    assert isinstance(svc.learning_service, LearningService)
    assert isinstance(svc.shadow_evaluation_service, ShadowEvaluationService)
