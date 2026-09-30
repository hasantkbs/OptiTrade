"""Tests for ml_training/training/. Real training on real synthetic
data for all four algorithms - no mocked model logic."""
import os
import tempfile

import numpy as np
import pytest

from ml_training.config import MLTrainingConfig
from ml_training.exceptions import ModelNotFittedError, UnknownAlgorithmError
from ml_training.models import ModelAlgorithm, TaskType
from ml_training.training.interfaces import ModelTrainerProtocol
from ml_training.training.service import create_trainer

_FEATURE_NAMES = ["f0", "f1", "f2", "f3", "f4"]


@pytest.fixture(scope="module")
def data():
    rng = np.random.RandomState(42)
    X = rng.rand(300, 5)
    y_class = (X[:, 0] + X[:, 1] > 1).astype(int)
    y_reg = X[:, 0] * 10 + X[:, 1] * 5 + rng.randn(300) * 0.1
    return {
        "X_train": X[:200], "X_val": X[200:250], "X_test": X[250:],
        "y_train_c": y_class[:200], "y_val_c": y_class[200:250], "y_test_c": y_class[250:],
        "y_train_r": y_reg[:200], "y_val_r": y_reg[200:250], "y_test_r": y_reg[250:],
    }


@pytest.mark.parametrize("algorithm", list(ModelAlgorithm))
class TestEveryAlgorithmSharesTheSameInterface:
    def test_fit_and_predict_classification(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
        trainer.fit(data["X_train"], data["y_train_c"], data["X_val"], data["y_val_c"])
        preds = trainer.predict(data["X_test"])
        assert preds.shape == (50,)
        assert set(np.unique(preds)) <= {0, 1}

    def test_fit_and_predict_regression(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.REGRESSION, _FEATURE_NAMES, {"n_estimators": 20})
        trainer.fit(data["X_train"], data["y_train_r"], data["X_val"], data["y_val_r"])
        preds = trainer.predict(data["X_test"])
        assert preds.shape == (50,)
        # A reasonably fit regressor on this near-linear synthetic
        # target should correlate strongly with the true values.
        correlation = np.corrcoef(preds, data["y_test_r"])[0, 1]
        assert correlation > 0.8

    def test_predict_proba_for_classification(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
        trainer.fit(data["X_train"], data["y_train_c"])
        proba = trainer.predict_proba(data["X_test"])
        assert proba.shape == (50, 2)
        assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-6)

    def test_predict_proba_raises_for_regression(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.REGRESSION, _FEATURE_NAMES, {"n_estimators": 20})
        trainer.fit(data["X_train"], data["y_train_r"])
        with pytest.raises(ValueError):
            trainer.predict_proba(data["X_test"])

    def test_feature_importance_sums_to_one(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
        trainer.fit(data["X_train"], data["y_train_c"])
        importance = trainer.feature_importance()
        assert set(importance.keys()) == set(_FEATURE_NAMES)
        assert sum(importance.values()) == pytest.approx(1.0, abs=1e-6)

    def test_predict_before_fit_raises(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES)
        with pytest.raises(ModelNotFittedError):
            trainer.predict(data["X_test"])

    def test_feature_importance_before_fit_raises(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES)
        with pytest.raises(ModelNotFittedError):
            trainer.feature_importance()

    def test_save_before_fit_raises(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES)
        with pytest.raises(ModelNotFittedError):
            trainer.save("/tmp/should-not-be-created.joblib")

    def test_save_and_load_round_trip_produces_identical_predictions(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 20})
        trainer.fit(data["X_train"], data["y_train_c"])
        preds_before = trainer.predict(data["X_test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "model.joblib")
            trainer.save(path)

            fresh_trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, [])
            fresh_trainer.load(path)
            preds_after = fresh_trainer.predict(data["X_test"])

        assert np.array_equal(preds_before, preds_after)
        assert fresh_trainer.feature_names == _FEATURE_NAMES

    def test_hyperparameters_override_defaults(self, algorithm, data):
        trainer = create_trainer(
            algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES,
            hyperparameters={"random_state": 999, "n_estimators": 10},
            config=MLTrainingConfig(random_state=1),
        )
        trainer.fit(data["X_train"], data["y_train_c"])
        assert trainer.hyperparameters["random_state"] == 999

    def test_satisfies_model_trainer_protocol(self, algorithm, data):
        trainer = create_trainer(algorithm, TaskType.CLASSIFICATION, _FEATURE_NAMES)
        assert isinstance(trainer, ModelTrainerProtocol)


def test_create_trainer_raises_for_unknown_algorithm():
    with pytest.raises(UnknownAlgorithmError):
        create_trainer("not_a_real_algorithm", TaskType.CLASSIFICATION, _FEATURE_NAMES)
