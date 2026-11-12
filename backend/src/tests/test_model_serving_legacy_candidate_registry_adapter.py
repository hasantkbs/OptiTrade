"""
Tests for model_serving/legacy_candidate_registry_adapter.py (Task
0.2-B): registers a Task 0.2-A candidate artifact into
`ml_training.registry` as a CANDIDATE row only.

Uses a fake, duck-typed registry service (never constructs the real
`ModelRegistryService()` - that eagerly triggers Postgres DDL/connection
at construction, see `ml_training/registry/service.py`'s own
docstring) and a real, UNFIT `XGBClassifier` (constructed only to
exercise `get_params()` - never `.fit()`, never trained on any data,
real or synthetic) written to a `tmp_path` joblib file. No real
database, no real training, and no real/live model artifact anywhere
in this file.
"""
import math
import os
from datetime import datetime, timezone

import joblib
import pytest
from xgboost import XGBClassifier

from ml_training.exceptions import MLTrainingPersistenceError
from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState
from model_serving.exceptions import (
    CandidateArtifactUnreadableError,
    CandidateRegistrationConflictError,
    CandidateRegistrationError,
)
from model_serving.legacy_candidate_registry_adapter import (
    _extract_numeric_hyperparameters,
    register_legacy_candidate,
)


class _FakeRegistryService:
    """Deliberately exposes only `get`/`register` - the adapter must
    never call anything else (promote_to_active/start_shadow/archive),
    which this file's own tests assert by checking those attributes
    simply don't exist here."""

    def __init__(self, existing=None, get_raises=None, register_raises=None):
        self._existing = dict(existing or {})
        self._get_raises = get_raises
        self._register_raises = register_raises
        self.registered_entries = []
        self.get_calls = []

    def get(self, model_id):
        self.get_calls.append(model_id)
        if self._get_raises is not None:
            raise self._get_raises
        return self._existing.get(model_id)

    def register(self, entry):
        if self._register_raises is not None:
            raise self._register_raises
        self.registered_entries.append(entry)
        self._existing[entry.model_id] = entry  # matches the real repository: a subsequent get() finds it
        return entry


class _FakeFittedModel:
    """A minimal get_params()-only double for directly unit-testing
    _extract_numeric_hyperparameters with controlled, deterministic
    values (NaN/inf in particular) - no real XGBoost involved."""

    def __init__(self, params):
        self._params = params

    def get_params(self):
        return self._params


class _ConcurrentRaceRegistryService:
    """Simulates the losing side of a concurrent registration race (not
    a real concurrent Postgres race - a deterministic, sequential
    simulation of it): the adapter's own first get() call (the
    pre-register check) returns None, register() then raises (as the
    real repository's UNIQUE constraint would on the loser), and the
    adapter's SECOND get() call (its recovery lookup) returns whatever
    `recovery_result` says (a winning row, a conflicting row, or None),
    or raises `recovery_raises` if the recovery lookup itself fails."""

    def __init__(self, register_raises, recovery_result=None, recovery_raises=None):
        self._register_raises = register_raises
        self._recovery_result = recovery_result
        self._recovery_raises = recovery_raises
        self.get_call_count = 0
        self.register_called = False

    def get(self, model_id):
        self.get_call_count += 1
        if self.get_call_count == 1:
            return None
        if self._recovery_raises is not None:
            raise self._recovery_raises
        return self._recovery_result

    def register(self, entry):
        self.register_called = True
        raise self._register_raises


def _package(accuracy: float = 0.60, forward_days: int = 5, feature_names=None) -> dict:
    model = XGBClassifier(
        n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8,
        colsample_bytree=0.8, min_child_weight=5, gamma=0.1, eval_metric="logloss",
        random_state=42, n_jobs=-1,
    )  # never .fit() - get_params() works on an unfit estimator
    return {
        "model": model,
        "feature_names": feature_names or ["rsi", "macd_diff", "bollinger_pb"],
        "lookback": 60, "forward_days": forward_days, "threshold": 1.0,
        "cv_accuracy_mean": accuracy, "cv_accuracy_std": 0.01,
        "train_samples": 100, "test_samples": 25, "train_end_date": None,
    }


@pytest.fixture
def candidate_id():
    return "20261112T000000123456_abcd1234"


@pytest.fixture
def artifact_path(tmp_path, candidate_id):
    path = tmp_path / f"xgb_signal_model_candidate_{candidate_id}.joblib"
    joblib.dump(_package(), path)
    return str(path)


@pytest.fixture
def created_at():
    return datetime(2026, 11, 12, tzinfo=timezone.utc)


# ── Successful registration + metadata mapping (CTO-approved mapping) ─────

def test_successful_registration_returns_the_registered_entry(candidate_id, artifact_path, created_at):
    fake_service = _FakeRegistryService()

    entry = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert entry is fake_service.registered_entries[0]


def test_promotion_state_is_always_candidate(candidate_id, artifact_path, created_at):
    fake_service = _FakeRegistryService()

    entry = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert entry.promotion_state == PromotionState.CANDIDATE


def test_no_promotion_or_shadow_deployment_method_exists_to_be_called(candidate_id, artifact_path, created_at):
    """The fake service only implements get()/register() - if the
    adapter ever tried to promote/shadow-deploy, it would need methods
    that simply don't exist on this fake, proving it never tries."""
    fake_service = _FakeRegistryService()

    register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert not hasattr(fake_service, "promote_to_active")
    assert not hasattr(fake_service, "start_shadow")
    assert not hasattr(fake_service, "archive")


def test_metadata_mapping_matches_the_approved_convention(candidate_id, artifact_path, created_at):
    fake_service = _FakeRegistryService()

    entry = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert entry.model_id == f"legacy_xgb_signal_{candidate_id}"
    assert entry.engine_name == f"MLModel:{entry.model_id}"
    assert entry.engine_version == candidate_id
    assert entry.version == candidate_id
    assert entry.algorithm == ModelAlgorithm.XGBOOST
    assert entry.label_name == LabelName.DIRECTION
    assert entry.horizon_days == 5
    assert entry.training_date == created_at
    assert entry.feature_list == ["rsi", "macd_diff", "bollinger_pb"]
    assert entry.artifact_path == artifact_path
    assert entry.approved_by is None
    assert entry.promoted_at is None


def test_hyperparameters_are_the_real_models_numeric_get_params_subset(candidate_id, artifact_path, created_at):
    fake_service = _FakeRegistryService()

    entry = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert entry.hyperparameters["n_estimators"] == 300.0
    assert entry.hyperparameters["max_depth"] == 5.0
    assert entry.hyperparameters["min_child_weight"] == 5.0
    assert entry.hyperparameters["learning_rate"] == pytest.approx(0.05)
    assert entry.hyperparameters["subsample"] == pytest.approx(0.8)
    assert entry.hyperparameters["colsample_bytree"] == pytest.approx(0.8)
    assert entry.hyperparameters["gamma"] == pytest.approx(0.1)
    assert entry.hyperparameters["random_state"] == 42.0
    # Non-numeric get_params() entries (str/None/bool) must never appear -
    # confirmed empirically before implementation that the raw dict fails
    # Pydantic validation against Dict[str, float].
    assert "eval_metric" not in entry.hyperparameters  # was the string "logloss"
    assert "objective" not in entry.hyperparameters  # was the string "binary:logistic"
    assert "booster" not in entry.hyperparameters  # was None
    assert "enable_categorical" not in entry.hyperparameters  # was the bool False


def test_accuracy_maps_without_fabricating_any_other_metric(candidate_id, artifact_path, created_at):
    fake_service = _FakeRegistryService()

    entry = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert entry.metrics.accuracy == 0.60
    # Never computed by the legacy trainer - must stay at Pydantic defaults,
    # never fabricated.
    assert entry.metrics.precision == 0.0
    assert entry.metrics.recall == 0.0
    assert entry.metrics.f1 == 0.0
    assert entry.metrics.roc_auc is None
    assert entry.metrics.sharpe_ratio == 0.0
    assert entry.metrics.sortino_ratio == 0.0
    assert entry.metrics.profit_factor == 0.0


# ── Idempotency / conflict ──────────────────────────────────────────────────

def test_retrying_the_same_candidate_is_idempotent(candidate_id, artifact_path, created_at):
    fake_service = _FakeRegistryService()
    first = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    second = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert second is first
    assert len(fake_service.registered_entries) == 1  # register() called exactly once, not twice


def test_same_model_id_with_a_different_artifact_path_raises_conflict(candidate_id, artifact_path, created_at):
    model_id = f"legacy_xgb_signal_{candidate_id}"
    conflicting_entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.XGBOOST, version=candidate_id,
        feature_list=["x"], label_name=LabelName.DIRECTION, horizon_days=5,
        training_date=created_at, engine_name=f"MLModel:{model_id}", engine_version=candidate_id,
        artifact_path="/some/other/completely-different-artifact.joblib",
    )
    fake_service = _FakeRegistryService(existing={model_id: conflicting_entry})

    with pytest.raises(CandidateRegistrationConflictError):
        register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert fake_service.registered_entries == []  # never attempted to overwrite the conflicting record


# ── Database failure propagation ────────────────────────────────────────────

def test_database_failure_during_duplicate_lookup_propagates_as_registration_error(
    candidate_id, artifact_path, created_at,
):
    fake_service = _FakeRegistryService(get_raises=MLTrainingPersistenceError("simulated: connection refused"))

    with pytest.raises(CandidateRegistrationError):
        register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)


def test_database_failure_during_insert_propagates_as_registration_error(candidate_id, artifact_path, created_at):
    fake_service = _FakeRegistryService(register_raises=MLTrainingPersistenceError("simulated: insert failed"))

    with pytest.raises(CandidateRegistrationError):
        register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert fake_service.registered_entries == []


# ── Missing / unreadable / corrupt artifact, and id/filename mismatch ─────

def test_missing_artifact_fails_before_any_registry_call(candidate_id, created_at, tmp_path):
    missing_path = str(tmp_path / f"xgb_signal_model_candidate_{candidate_id}.joblib")
    fake_service = _FakeRegistryService()

    with pytest.raises(CandidateArtifactUnreadableError):
        register_legacy_candidate(candidate_id, missing_path, created_at, registry_service=fake_service)

    assert fake_service.get_calls == []
    assert fake_service.registered_entries == []


def test_corrupt_artifact_fails(candidate_id, created_at, tmp_path):
    corrupt_path = tmp_path / f"xgb_signal_model_candidate_{candidate_id}.joblib"
    corrupt_path.write_bytes(b"not a valid joblib file")
    fake_service = _FakeRegistryService()

    with pytest.raises(CandidateArtifactUnreadableError):
        register_legacy_candidate(candidate_id, str(corrupt_path), created_at, registry_service=fake_service)

    assert fake_service.registered_entries == []


def test_candidate_id_filename_mismatch_fails_before_any_file_read(created_at, tmp_path):
    real_path = tmp_path / "xgb_signal_model_candidate_totally-different-id.joblib"
    joblib.dump(_package(), real_path)
    fake_service = _FakeRegistryService()

    with pytest.raises(CandidateArtifactUnreadableError):
        register_legacy_candidate("some-other-id", str(real_path), created_at, registry_service=fake_service)

    assert fake_service.get_calls == []
    assert fake_service.registered_entries == []


# ── Candidate artifact is never mutated ─────────────────────────────────────

def test_artifact_file_is_never_modified_moved_or_deleted(candidate_id, artifact_path, created_at):
    fake_service = _FakeRegistryService()
    original_bytes = open(artifact_path, "rb").read()
    original_mtime = os.path.getmtime(artifact_path)

    register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert os.path.exists(artifact_path)
    assert open(artifact_path, "rb").read() == original_bytes
    assert os.path.getmtime(artifact_path) == original_mtime


def test_artifact_file_is_never_mutated_even_on_a_conflict(candidate_id, artifact_path, created_at):
    model_id = f"legacy_xgb_signal_{candidate_id}"
    conflicting_entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.XGBOOST, version=candidate_id,
        feature_list=["x"], label_name=LabelName.DIRECTION, horizon_days=5,
        training_date=created_at, engine_name=f"MLModel:{model_id}", engine_version=candidate_id,
        artifact_path="/some/other/completely-different-artifact.joblib",
    )
    fake_service = _FakeRegistryService(existing={model_id: conflicting_entry})
    original_bytes = open(artifact_path, "rb").read()

    with pytest.raises(CandidateRegistrationConflictError):
        register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert open(artifact_path, "rb").read() == original_bytes


# ── Non-finite hyperparameter exclusion ─────────────────────────────────────

def test_ordinary_int_and_float_params_are_retained_as_floats():
    model = _FakeFittedModel({"n_estimators": 300, "learning_rate": 0.05})

    result = _extract_numeric_hyperparameters(model)

    assert result == {"n_estimators": 300.0, "learning_rate": 0.05}
    assert all(isinstance(v, float) for v in result.values())


def test_boolean_values_are_excluded():
    model = _FakeFittedModel({"enable_categorical": False, "some_flag": True, "n_estimators": 300})

    result = _extract_numeric_hyperparameters(model)

    assert result == {"n_estimators": 300.0}


def test_nan_is_excluded():
    model = _FakeFittedModel({"missing": float("nan"), "n_estimators": 300})

    result = _extract_numeric_hyperparameters(model)

    assert "missing" not in result
    assert result == {"n_estimators": 300.0}


def test_positive_infinity_is_excluded():
    model = _FakeFittedModel({"weird_param": float("inf"), "n_estimators": 300})

    result = _extract_numeric_hyperparameters(model)

    assert "weird_param" not in result
    assert result == {"n_estimators": 300.0}


def test_negative_infinity_is_excluded():
    model = _FakeFittedModel({"weird_param": float("-inf"), "n_estimators": 300})

    result = _extract_numeric_hyperparameters(model)

    assert "weird_param" not in result
    assert result == {"n_estimators": 300.0}


def test_real_xgboost_mapping_remains_correct_with_non_finite_exclusion(candidate_id, artifact_path, created_at):
    """End-to-end through register_legacy_candidate against a real
    (unfit) XGBClassifier - confirms the non-finite filter doesn't break
    the existing real-parameter mapping, and that XGBoost's own real
    missing=nan default is now excluded too (previously untested either
    way, since no assertion on "missing" existed before this task)."""
    fake_service = _FakeRegistryService()

    entry = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert entry.hyperparameters["n_estimators"] == 300.0
    assert entry.hyperparameters["max_depth"] == 5.0
    assert entry.hyperparameters["min_child_weight"] == 5.0
    assert entry.hyperparameters["learning_rate"] == pytest.approx(0.05)
    assert entry.hyperparameters["subsample"] == pytest.approx(0.8)
    assert entry.hyperparameters["colsample_bytree"] == pytest.approx(0.8)
    assert entry.hyperparameters["gamma"] == pytest.approx(0.1)
    assert entry.hyperparameters["random_state"] == 42.0
    assert "missing" not in entry.hyperparameters  # was nan - now explicitly excluded
    assert all(math.isfinite(v) for v in entry.hyperparameters.values())


# ── Concurrent duplicate registration recovery ──────────────────────────────
#
# These simulate the LOSING side of a concurrent registration race
# deterministically (via _ConcurrentRaceRegistryService) - they do not
# spin up real threads/processes or a real PostgreSQL unique-constraint
# race. No claim is made anywhere in this file that a real concurrent
# Postgres race was exercised.

def test_concurrent_race_recovery_returns_existing_entry_when_path_matches(candidate_id, artifact_path, created_at):
    model_id = f"legacy_xgb_signal_{candidate_id}"
    winning_entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.XGBOOST, version=candidate_id,
        feature_list=["rsi"], label_name=LabelName.DIRECTION, horizon_days=5,
        training_date=created_at, engine_name=f"MLModel:{model_id}", engine_version=candidate_id,
        artifact_path=artifact_path,  # the SAME path as the candidate being registered now
    )
    fake_service = _ConcurrentRaceRegistryService(
        register_raises=MLTrainingPersistenceError("simulated: unique constraint violation"),
        recovery_result=winning_entry,
    )

    result = register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert result is winning_entry
    assert fake_service.get_call_count == 2  # initial check + recovery lookup
    assert fake_service.register_called is True


def test_concurrent_race_recovery_raises_conflict_when_path_differs(candidate_id, artifact_path, created_at):
    model_id = f"legacy_xgb_signal_{candidate_id}"
    conflicting_entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.XGBOOST, version=candidate_id,
        feature_list=["x"], label_name=LabelName.DIRECTION, horizon_days=5,
        training_date=created_at, engine_name=f"MLModel:{model_id}", engine_version=candidate_id,
        artifact_path="/some/other/different-artifact.joblib",
    )
    fake_service = _ConcurrentRaceRegistryService(
        register_raises=MLTrainingPersistenceError("simulated: unique constraint violation"),
        recovery_result=conflicting_entry,
    )

    with pytest.raises(CandidateRegistrationConflictError):
        register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)


def test_concurrent_race_recovery_raises_registration_error_when_no_row_found(candidate_id, artifact_path, created_at):
    """The register() failure was real (no row materialized even after
    the recovery lookup) - a genuine outage, not a benign race - must
    still be reported, never swallowed as success."""
    fake_service = _ConcurrentRaceRegistryService(
        register_raises=MLTrainingPersistenceError("simulated: insert failed"),
        recovery_result=None,
    )

    with pytest.raises(CandidateRegistrationError) as excinfo:
        register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert isinstance(excinfo.value.__cause__, MLTrainingPersistenceError)


def test_concurrent_race_recovery_lookup_failure_raises_registration_error(candidate_id, artifact_path, created_at):
    """If the recovery lookup itself fails (a second, independent
    database problem), the failure must still propagate as a
    CandidateRegistrationError, with the recovery exception preserved
    as its __cause__ - never swallowed, never misreported as success."""
    fake_service = _ConcurrentRaceRegistryService(
        register_raises=MLTrainingPersistenceError("simulated: insert failed"),
        recovery_raises=MLTrainingPersistenceError("simulated: connection dropped during recovery"),
    )

    with pytest.raises(CandidateRegistrationError) as excinfo:
        register_legacy_candidate(candidate_id, artifact_path, created_at, registry_service=fake_service)

    assert isinstance(excinfo.value.__cause__, MLTrainingPersistenceError)
    assert "connection dropped during recovery" in str(excinfo.value.__cause__)
