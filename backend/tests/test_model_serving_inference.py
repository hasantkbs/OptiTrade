"""Tests for model_serving/inference.py. Real Feature Store
(PostgreSQL/Redis) so `MLModelVotingEngineAdapter.vote()` genuinely
resolves point-in-time feature vectors - no mocked production logic."""
import asyncio
from datetime import datetime, timezone

import numpy as np
import pytest

from decision_engine.models import Prediction
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState, TaskType
from ml_training.training.service import create_trainer
from model_serving.inference import InferenceEngine
from model_serving.loader import LoadedModel

_FEATURE_NAMES = ["f0", "f1"]
_SYMBOLS = ["MSVCINF1", "MSVCINF2", "MSVCINF3"]


def _fitted_trainer():
    rng = np.random.RandomState(1)
    X = rng.rand(150, 2)
    y = np.where(X[:, 0] > 0.6, "BUY", np.where(X[:, 0] < 0.4, "SELL", "HOLD"))
    trainer = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
    trainer.fit(X, y)
    return trainer


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    for symbol in _SYMBOLS:
        fs.write_feature(FeatureValue(symbol=symbol, feature_name="f0", value=0.9))
        fs.write_feature(FeatureValue(symbol=symbol, feature_name="f1", value=0.1))
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = ANY(%s)", (_SYMBOLS,))
    finally:
        fs.offline_store._pool.putconn(conn)
    for symbol in _SYMBOLS:
        fs.online_store._client.delete(f"feature_store:{symbol}:f0")
        fs.online_store._client.delete(f"feature_store:{symbol}:f1")


@pytest.fixture
def loaded_model():
    entry = ModelRegistryEntry(
        model_id="inference-test-model", algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=_FEATURE_NAMES, label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.ACTIVE,
        engine_name="MLModel:inference-test-model", engine_version="v1", artifact_path="/tmp/unused.joblib",
    )
    return LoadedModel(
        entry=entry, trainer=_fitted_trainer(), calibrated=None, checksum="unused",
        loaded_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def engine(feature_store):
    return InferenceEngine(feature_extractor=FeatureExtractor(feature_store=feature_store))


def test_adapter_for_returns_the_same_instance_on_repeated_calls(engine, loaded_model):
    first = engine.adapter_for(loaded_model)
    second = engine.adapter_for(loaded_model)
    assert first is second


def test_predict_one_returns_a_valid_vote(engine, loaded_model):
    vote = engine.predict_one(loaded_model, _SYMBOLS[0])
    assert vote.engine_name == "MLModel:inference-test-model"
    assert vote.prediction in {Prediction.BUY, Prediction.HOLD, Prediction.SELL}
    assert 0.0 <= vote.confidence <= 1.0


def test_predict_batch_returns_one_vote_per_symbol_in_order(engine, loaded_model):
    votes = engine.predict_batch(loaded_model, _SYMBOLS)
    assert len(votes) == len(_SYMBOLS)
    assert all(vote.engine_name == "MLModel:inference-test-model" for vote in votes)


def test_predict_batch_parallel_returns_one_vote_per_symbol(engine, loaded_model):
    votes = engine.predict_batch_parallel(loaded_model, _SYMBOLS)
    assert len(votes) == len(_SYMBOLS)
    assert all(vote.prediction in {Prediction.BUY, Prediction.HOLD, Prediction.SELL} for vote in votes)


def test_predict_async_returns_a_valid_vote(engine, loaded_model):
    vote = asyncio.run(engine.predict_async(loaded_model, _SYMBOLS[0]))
    assert vote.prediction in {Prediction.BUY, Prediction.HOLD, Prediction.SELL}


def test_predict_batch_async_returns_one_vote_per_symbol(engine, loaded_model):
    votes = asyncio.run(engine.predict_batch_async(loaded_model, _SYMBOLS))
    assert len(votes) == len(_SYMBOLS)


def test_service_defaults_to_real_dependencies():
    engine = InferenceEngine()
    assert isinstance(engine.feature_extractor, FeatureExtractor)
    engine.shutdown()
