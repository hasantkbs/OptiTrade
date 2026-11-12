"""
Regression tests for research/ml_trainer.py's train() dispatch logic
(Task 0.2-A CTO review follow-up): the default-`output_suffix` call
(main.py's self_evolution_loop) must route to write_candidate_artifact()
and must NEVER call _deploy_if_not_regressed(); an explicit, non-empty
output_suffix (the existing manual/research CLI usage) must keep
calling _deploy_if_not_regressed() and must NEVER call
write_candidate_artifact().

No real training and no network access occur anywhere in this file:
- `xgboost.XGBClassifier` and `sklearn.model_selection.cross_val_score`
  are replaced with trivial fakes (no real model fitting happens).
- `build_dataset` is replaced with a tiny, fixed, in-memory synthetic
  dataset (no yfinance/network call).
- The working directory is a fresh `tmp_path` for every test, so
  train()'s own unconditional `os.makedirs("../model_artifacts", ...)`
  can never reach the real repository or the live model artifact.
- `write_candidate_artifact`/`_deploy_if_not_regressed` themselves are
  monkeypatched to recording spies for these tests - their own internal
  correctness is already covered by test_ml_trainer_candidate_artifacts.py
  and test_ml_trainer_deploy_safety.py; this file only proves WHICH one
  train() calls for a given output_suffix.
"""
import numpy as np
import pytest

import research.ml_trainer as ml_trainer


class _FakeXGBClassifier:
    """No real fitting/prediction - just enough surface for train()'s
    own control flow (feature_importances_, fit, predict, predict_proba)
    to run without touching a real XGBoost model."""

    def __init__(self, **kwargs):
        self.feature_importances_ = [0.1] * len(ml_trainer.FEATURE_NAMES)

    def fit(self, X, y, verbose=False):
        return self

    def predict(self, X):
        return [0] * len(X)

    def predict_proba(self, X):
        return np.tile(np.array([0.5, 0.5]), (len(X), 1))


def _fake_build_dataset(symbol, train_end_date=None):
    """A fixed, tiny, balanced synthetic dataset - no yfinance call, no
    real market data, identical regardless of `symbol`/`train_end_date`."""
    X = np.tile(np.arange(len(ml_trainer.FEATURE_NAMES), dtype=np.float32), (40, 1))
    y = np.array([0, 1] * 20, dtype=np.int32)
    return X, y


@pytest.fixture(autouse=True)
def _no_real_training_network_or_filesystem_leakage(monkeypatch, tmp_path):
    monkeypatch.setattr("xgboost.XGBClassifier", _FakeXGBClassifier)
    monkeypatch.setattr(
        "sklearn.model_selection.cross_val_score",
        lambda *a, **kw: np.array([0.6, 0.6, 0.6, 0.6, 0.6]),
    )
    monkeypatch.setattr(ml_trainer, "build_dataset", _fake_build_dataset)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def _routing_spies(monkeypatch):
    calls = []

    def _fake_write_candidate_artifact(package, joblib_module, candidates_dir=None):
        calls.append("write_candidate_artifact")
        return ml_trainer.CandidateArtifact(candidate_id="fake-id", path="fake-path", created_at=None)

    def _fake_deploy_if_not_regressed(model_path, package, joblib_module):
        calls.append("_deploy_if_not_regressed")
        return True

    monkeypatch.setattr(ml_trainer, "write_candidate_artifact", _fake_write_candidate_artifact)
    monkeypatch.setattr(ml_trainer, "_deploy_if_not_regressed", _fake_deploy_if_not_regressed)
    return calls


def test_train_with_default_output_suffix_calls_write_candidate_artifact_only(_routing_spies):
    ml_trainer.train()  # default output_suffix=""

    assert _routing_spies == ["write_candidate_artifact"]


def test_train_with_explicit_output_suffix_calls_deploy_if_not_regressed_only(_routing_spies):
    ml_trainer.train(output_suffix="_oos_test")

    assert _routing_spies == ["_deploy_if_not_regressed"]


def test_train_with_default_output_suffix_returns_the_candidate_artifact(_routing_spies):
    """Task 0.2-B: main.py's self_evolution_loop needs this return value
    to register the candidate - previously discarded after printing."""
    result = ml_trainer.train()

    assert isinstance(result, ml_trainer.CandidateArtifact)
    assert result.candidate_id == "fake-id"
    assert result.path == "fake-path"


def test_train_with_explicit_output_suffix_returns_none(_routing_spies):
    """The explicit-suffix (manual/research) path deploys via
    _deploy_if_not_regressed instead - there is no CandidateArtifact for
    a caller to register, so it must return None, not a stale/wrong value."""
    result = ml_trainer.train(output_suffix="_oos_test")

    assert result is None
