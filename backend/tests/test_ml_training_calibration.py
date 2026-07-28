"""Tests for ml_training/calibration/. Real sklearn calibration, real
PostgreSQL persistence."""
import os
import tempfile

import numpy as np
import pytest

from ml_training.calibration.calibrator import ModelCalibrator
from ml_training.calibration.repository import CalibrationRepository
from ml_training.calibration.service import CalibrationService
from ml_training.models import CalibrationMethod, ModelAlgorithm, TaskType
from ml_training.training.service import create_trainer

_FEATURE_NAMES = ["f0", "f1", "f2", "f3", "f4"]


@pytest.fixture(scope="module")
def split_data():
    rng = np.random.RandomState(0)
    X = rng.rand(400, 5)
    y = (X[:, 0] + X[:, 1] > 1).astype(int)
    return {
        "X_train": X[:200], "X_cal": X[200:300], "X_test": X[300:],
        "y_train": y[:200], "y_cal": y[200:300], "y_test": y[300:],
    }


@pytest.fixture(scope="module")
def fitted_trainer(split_data):
    trainer = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 30})
    trainer.fit(split_data["X_train"], split_data["y_train"])
    return trainer


# ─────────────────────────────────────────────────────────────────────────
# calibrator.py
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method", list(CalibrationMethod))
def test_calibrate_produces_a_fitted_calibrated_model(method, split_data, fitted_trainer):
    calibrator = ModelCalibrator()
    calibrated = calibrator.calibrate(fitted_trainer, split_data["X_cal"], split_data["y_cal"], method)
    proba = calibrated.predict_proba(split_data["X_test"])
    assert proba.shape == (len(split_data["X_test"]), 2)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-6)


def test_calibrate_raises_for_regression_trainer(split_data):
    rng = np.random.RandomState(2)
    X, y = rng.rand(100, 5), rng.rand(100)
    reg_trainer = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.REGRESSION, _FEATURE_NAMES, {"n_estimators": 10})
    reg_trainer.fit(X, y)
    calibrator = ModelCalibrator()
    with pytest.raises(ValueError):
        calibrator.calibrate(reg_trainer, split_data["X_cal"], split_data["y_cal"], CalibrationMethod.ISOTONIC)


def test_calibrate_raises_when_trainer_not_fitted(split_data):
    trainer = create_trainer(ModelAlgorithm.RANDOM_FOREST, TaskType.CLASSIFICATION, _FEATURE_NAMES)
    calibrator = ModelCalibrator()
    with pytest.raises(ValueError):
        calibrator.calibrate(trainer, split_data["X_cal"], split_data["y_cal"], CalibrationMethod.ISOTONIC)


# ─────────────────────────────────────────────────────────────────────────
# service.py (real Postgres)
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def repository():
    repo = CalibrationRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_calibration_results WHERE model_id LIKE 'calib-svc-test%'")
    finally:
        repo._pool.putconn(conn)


def test_calibrate_and_save_persists_result_and_artifact(split_data, fitted_trainer, repository):
    svc = CalibrationService(repository=repository)
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "calibrated.joblib")
        result = svc.calibrate_and_save(
            "calib-svc-test", fitted_trainer, split_data["X_cal"], split_data["y_cal"],
            split_data["X_test"], split_data["y_test"], CalibrationMethod.ISOTONIC, path,
        )
        assert os.path.exists(path)
        assert result.calibration_error_before >= 0.0
        assert result.calibration_error_after >= 0.0

    latest = svc.get_latest("calib-svc-test")
    assert latest.method == CalibrationMethod.ISOTONIC
    assert len(svc.list_for_model("calib-svc-test")) == 1


def test_get_latest_returns_none_when_no_history(repository):
    svc = CalibrationService(repository=repository)
    assert svc.get_latest("calib-svc-test-nonexistent") is None


def test_service_defaults_to_real_dependencies():
    svc = CalibrationService()
    assert isinstance(svc.repository, CalibrationRepository)
