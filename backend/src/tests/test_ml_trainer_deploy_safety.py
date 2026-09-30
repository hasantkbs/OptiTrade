"""
Regression tests for the production audit's "Production's real
model-refresh path bypasses every safety mechanism that was built"
Critical finding.

research/ml_trainer.py's train() previously called
`joblib.dump(package, model_path)` directly, unconditionally
overwriting the live-served model file with zero comparison against
the model it replaced and zero rollback capability - a regression in
a scheduled retrain (self_evolution_loop, once a day) would silently
ship to production. `_deploy_if_not_regressed` closes that: it refuses
to deploy a model that scores meaningfully worse than the one it would
replace, keeps a `.bak` copy of the previous live model before
swapping, and writes atomically (temp file + os.replace) so a reader
never observes a partially-written file.

Training a real model requires real network data (yfinance) and is
genuinely expensive/nondeterministic - per this project's testing
convention that's acceptable to avoid here; these tests exercise
`_deploy_if_not_regressed` directly against small in-memory "model"
packages and a real filesystem/joblib round-trip, which is exactly
where the audited bug lives.
"""
import os

import joblib
import pytest

from research.ml_trainer import MAX_ACCURACY_REGRESSION, _deploy_if_not_regressed


def _package(accuracy: float, marker: str) -> dict:
    return {"model": marker, "cv_accuracy_mean": accuracy, "cv_accuracy_std": 0.01}


@pytest.fixture
def model_path(tmp_path):
    return str(tmp_path / "xgb_signal_model.joblib")


def test_deploys_when_no_previous_model_exists(model_path):
    deployed = _deploy_if_not_regressed(model_path, _package(0.55, "first"), joblib)
    assert deployed is True
    assert joblib.load(model_path)["model"] == "first"
    assert not os.path.exists(model_path + ".bak")


def test_deploys_when_new_model_is_better(model_path):
    joblib.dump(_package(0.60, "old"), model_path)
    deployed = _deploy_if_not_regressed(model_path, _package(0.70, "new"), joblib)
    assert deployed is True
    assert joblib.load(model_path)["model"] == "new"
    assert joblib.load(model_path + ".bak")["model"] == "old"


def test_deploys_when_regression_is_within_tolerance(model_path):
    joblib.dump(_package(0.60, "old"), model_path)
    new_accuracy = 0.60 - MAX_ACCURACY_REGRESSION  # exactly at the tolerance boundary
    deployed = _deploy_if_not_regressed(model_path, _package(new_accuracy, "new"), joblib)
    assert deployed is True
    assert joblib.load(model_path)["model"] == "new"


def test_rejects_deploy_when_new_model_regresses_beyond_tolerance(model_path):
    joblib.dump(_package(0.60, "old"), model_path)
    deployed = _deploy_if_not_regressed(model_path, _package(0.50, "regressed"), joblib)
    assert deployed is False
    # the live model must be completely untouched by the rejected attempt
    assert joblib.load(model_path)["model"] == "old"
    assert not os.path.exists(model_path + ".bak")


def test_deploys_when_previous_model_is_unreadable(model_path):
    with open(model_path, "wb") as f:
        f.write(b"not a valid joblib file")
    deployed = _deploy_if_not_regressed(model_path, _package(0.10, "new"), joblib)
    assert deployed is True
    assert joblib.load(model_path)["model"] == "new"


def test_deploy_leaves_no_temp_file_behind(model_path):
    _deploy_if_not_regressed(model_path, _package(0.55, "first"), joblib)
    directory = os.path.dirname(model_path)
    leftovers = [f for f in os.listdir(directory) if f.endswith(".joblib.tmp")]
    assert leftovers == []
