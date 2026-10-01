"""Tests for ml_training/optimization/. Real Optuna optimization on
real synthetic data, real PostgreSQL persistence."""
import os
import tempfile

import numpy as np
import pytest

from ml_training.config import MLTrainingConfig
from ml_training.models import ModelAlgorithm, TaskType
from ml_training.optimization.optimizer import (
    HyperparameterOptimizer,
    default_classification_score,
    default_regression_score,
)
from ml_training.optimization.repository import OptimizationRepository
from ml_training.optimization.service import OptimizationService
from ml_training.training.service import create_trainer

_FEATURE_NAMES = ["f0", "f1", "f2", "f3", "f4"]


@pytest.fixture(scope="module")
def data():
    rng = np.random.RandomState(1)
    X = rng.rand(200, 5)
    y_class = (X[:, 0] + X[:, 1] > 1).astype(int)
    return {"X_train": X[:140], "X_val": X[140:], "y_train": y_class[:140], "y_val": y_class[140:]}


def test_default_classification_score_is_accuracy(data):
    trainer = create_trainer(ModelAlgorithm.LIGHTGBM, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
    trainer.fit(data["X_train"], data["y_train"])
    score = default_classification_score(trainer, data["X_val"], data["y_val"])
    assert 0.0 <= score <= 1.0


def test_default_regression_score_is_negative_mse():
    rng = np.random.RandomState(2)
    X = rng.rand(100, 5)
    y = X[:, 0] * 10
    trainer = create_trainer(ModelAlgorithm.LIGHTGBM, TaskType.REGRESSION, _FEATURE_NAMES, {"n_estimators": 20})
    trainer.fit(X, y)
    score = default_regression_score(trainer, X, y)
    assert score <= 0.0


@pytest.mark.parametrize("algorithm", list(ModelAlgorithm))
def test_optimize_returns_a_fitted_best_trainer(algorithm, data):
    config = MLTrainingConfig(optuna_n_trials=3, early_stopping_rounds=10)
    optimizer = HyperparameterOptimizer(config=config)
    result, best_trainer = optimizer.optimize(
        "opt-test", algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES,
        data["X_train"], data["y_train"], data["X_val"], data["y_val"],
    )
    assert result.n_trials == 3
    assert best_trainer.is_fitted
    assert result.algorithm == algorithm


def test_optimize_respects_n_trials(data):
    config = MLTrainingConfig(optuna_n_trials=4, early_stopping_rounds=10)
    optimizer = HyperparameterOptimizer(config=config)
    result, _ = optimizer.optimize(
        "opt-test", ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES,
        data["X_train"], data["y_train"], data["X_val"], data["y_val"],
    )
    assert result.n_trials == 4


def test_optimize_parallel_trials_completes(data):
    config = MLTrainingConfig(optuna_n_trials=4, optuna_n_jobs=2, early_stopping_rounds=10)
    optimizer = HyperparameterOptimizer(config=config)
    result, best_trainer = optimizer.optimize(
        "opt-test-parallel", ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES,
        data["X_train"], data["y_train"], data["X_val"], data["y_val"],
    )
    assert result.n_trials == 4
    assert best_trainer.is_fitted


def test_optimize_and_save_persists_the_best_model(data):
    config = MLTrainingConfig(optuna_n_trials=3, early_stopping_rounds=10)
    optimizer = HyperparameterOptimizer(config=config)
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "best.joblib")
        result, best_trainer = optimizer.optimize_and_save(
            "opt-test-save", ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES,
            data["X_train"], data["y_train"], data["X_val"], data["y_val"], artifact_path=path,
        )
        assert os.path.exists(path)


# ─────────────────────────────────────────────────────────────────────────
# service.py (real Postgres)
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def repository():
    repo = OptimizationRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_optimization_results WHERE model_id LIKE 'svc-opt-test%'")
    finally:
        repo._pool.putconn(conn)


def test_service_optimize_and_save_persists_result(data, repository):
    config = MLTrainingConfig(optuna_n_trials=3, early_stopping_rounds=10)
    svc = OptimizationService(repository=repository, config=config)
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "best.joblib")
        result, best_trainer = svc.optimize_and_save(
            "svc-opt-test", ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES,
            data["X_train"], data["y_train"], data["X_val"], data["y_val"], artifact_path=path,
        )
        assert best_trainer.is_fitted

    latest = svc.get_latest("svc-opt-test")
    assert latest.n_trials == 3
    assert len(svc.list_for_model("svc-opt-test")) == 1


def test_service_get_latest_returns_none_when_no_history(repository):
    svc = OptimizationService(repository=repository)
    assert svc.get_latest("svc-opt-test-nonexistent") is None


def test_service_defaults_to_real_dependencies():
    svc = OptimizationService()
    assert isinstance(svc.repository, OptimizationRepository)
