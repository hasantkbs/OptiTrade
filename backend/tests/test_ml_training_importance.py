"""Tests for ml_training/importance/. Real SHAP and permutation
importance, real PostgreSQL/Redis persistence."""
import numpy as np
import pytest

from feature_store.service import FeatureStoreService
from ml_training.importance import permutation_analyzer, shap_analyzer
from ml_training.importance.service import FeatureImportanceService
from ml_training.models import ImportanceMethod, ModelAlgorithm, TaskType
from ml_training.training.service import create_trainer
from research_lab.feature_analysis.repository import FeatureAnalysisRepository
from research_lab.feature_analysis.service import FeatureAnalysisService

_FEATURE_NAMES = ["f0", "f1", "f2", "f3", "f4"]
_MODEL_ID = "imp-test-model"


@pytest.fixture(scope="module")
def data():
    rng = np.random.RandomState(0)
    X = rng.rand(200, 5)
    y = (X[:, 0] + X[:, 1] > 1).astype(int)
    return X, y


@pytest.mark.parametrize("algorithm", list(ModelAlgorithm))
class TestShapAndPermutationAcrossAlgorithms:
    def _trainer(self, algorithm, data):
        X, y = data
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
        trainer.fit(X, y)
        return trainer

    def test_shap_importance_normalizes_to_one(self, algorithm, data):
        X, y = data
        trainer = self._trainer(algorithm, data)
        importance = shap_analyzer.compute_shap_importance(trainer._model, X[:30], _FEATURE_NAMES)
        assert set(importance.keys()) == set(_FEATURE_NAMES)
        assert sum(importance.values()) == pytest.approx(1.0, abs=1e-4)
        assert all(v >= 0 for v in importance.values())

    def test_permutation_importance_normalizes_to_one(self, algorithm, data):
        X, y = data
        trainer = self._trainer(algorithm, data)
        importance = permutation_analyzer.compute_permutation_importance(trainer, X, y, n_repeats=3)
        assert set(importance.keys()) == set(_FEATURE_NAMES)
        assert sum(importance.values()) == pytest.approx(1.0, abs=1e-4)
        assert all(v >= 0 for v in importance.values())


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_MODEL_ID,))
    finally:
        fs.offline_store._pool.putconn(conn)
    for method in ("shap", "permutation"):
        for name in _FEATURE_NAMES:
            fs.online_store._client.delete(f"feature_store:{_MODEL_ID}:{method}_importance:{name}")


@pytest.fixture
def feature_analysis_repository():
    repo = FeatureAnalysisRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM research_feature_importance WHERE symbol = %s", (_MODEL_ID,))
    finally:
        repo._pool.putconn(conn)


def test_compute_and_persist_shap_writes_to_feature_store_and_research_lab(
    data, feature_store, feature_analysis_repository,
):
    X, y = data
    trainer = create_trainer(ModelAlgorithm.LIGHTGBM, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
    trainer.fit(X, y)

    feature_analysis_service = FeatureAnalysisService(feature_store=feature_store, repository=feature_analysis_repository)
    svc = FeatureImportanceService(feature_store=feature_store, feature_analysis_service=feature_analysis_service)

    entries = svc.compute_and_persist_shap(_MODEL_ID, trainer, X[:30])
    assert len(entries) == 5
    assert all(entry.method == ImportanceMethod.SHAP for entry in entries)

    record = feature_store.get_latest_feature(_MODEL_ID, f"shap_importance:{_FEATURE_NAMES[0]}")
    assert record is not None

    research_lab_history = feature_analysis_repository.get_importance_history(_MODEL_ID, "MLModel:shap", _FEATURE_NAMES[0])
    assert len(research_lab_history) == 1


def test_compute_and_persist_permutation_writes_to_both_stores(data, feature_store, feature_analysis_repository):
    X, y = data
    trainer = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
    trainer.fit(X, y)

    feature_analysis_service = FeatureAnalysisService(feature_store=feature_store, repository=feature_analysis_repository)
    svc = FeatureImportanceService(feature_store=feature_store, feature_analysis_service=feature_analysis_service)

    entries = svc.compute_and_persist_permutation(_MODEL_ID, trainer, X, y)
    assert all(entry.method == ImportanceMethod.PERMUTATION for entry in entries)

    record = feature_store.get_latest_feature(_MODEL_ID, f"permutation_importance:{_FEATURE_NAMES[0]}")
    assert record is not None


def test_service_defaults_to_real_dependencies():
    svc = FeatureImportanceService()
    assert isinstance(svc.feature_store, FeatureStoreService)
    assert isinstance(svc.feature_analysis_service, FeatureAnalysisService)
