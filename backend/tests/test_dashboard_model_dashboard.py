"""Tests for dashboard/model_dashboard.py. Real PostgreSQL + Feature
Store throughout."""
from datetime import datetime, timedelta, timezone

import pytest

from dashboard.model_dashboard import ModelDashboardService
from dashboard.repository import DashboardRepository
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from learning.models import RollingWindow
from ml_training.calibration.repository import CalibrationRepository
from ml_training.models import (
    CalibrationMethod,
    CalibrationResult,
    LabelName,
    ModelAlgorithm,
    ModelRegistryEntry,
    PromotionState,
    TaskType,
    TrainingRun,
    TrainingRunStatus,
)
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.runs.repository import TrainingRunRepository
from model_serving.rollback import RollbackRepository
from research_lab.benchmarking.repository import BenchmarkRepository
from research_lab.models import BenchmarkResult, BenchmarkSubjectType, PromotionDecision, PromotionRecommendation
from research_lab.promotion.repository import PromotionRepository

_MODEL_ID_PREFIX = "model-dash-test"
_ENGINE_PREFIX = "model-dash-test-engine"


@pytest.fixture
def dashboard_repo():
    repository = DashboardRepository()
    yield repository
    repository.close()


@pytest.fixture
def registry_repo():
    return ModelRegistryRepository()


@pytest.fixture
def training_run_repo():
    return TrainingRunRepository()


@pytest.fixture
def calibration_repo():
    return CalibrationRepository()


@pytest.fixture
def benchmark_repo():
    return BenchmarkRepository()


@pytest.fixture
def promotion_repo():
    return PromotionRepository()


@pytest.fixture
def rollback_repo():
    return RollbackRepository()


@pytest.fixture
def feature_store():
    return FeatureStoreService()


@pytest.fixture
def service(dashboard_repo, feature_store):
    return ModelDashboardService(dashboard_repo, feature_store=feature_store)


def _cleanup(registry_repo, training_run_repo, calibration_repo, model_id):
    for repository, table, column in (
        (registry_repo, "ml_training_model_registry", "model_id"),
        (training_run_repo, "ml_training_runs", "model_id"),
        (calibration_repo, "ml_training_calibration_results", "model_id"),
    ):
        conn = repository._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(f"DELETE FROM {table} WHERE {column} = %s", (model_id,))
        finally:
            repository._pool.putconn(conn)


def test_active_models_reflects_registry(service, registry_repo, training_run_repo, calibration_repo):
    model_id = f"{_MODEL_ID_PREFIX}-active"
    engine_name = f"{_ENGINE_PREFIX}-active"
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.XGBOOST, version="v1", label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.ACTIVE,
        engine_name=engine_name, engine_version="v1", artifact_path="/tmp/m.joblib",
    )
    registry_repo.save(entry)
    try:
        view = service.build()
        active_ids = {m.model_id for m in view.active_models}
        assert model_id in active_ids
        matched = next(m for m in view.active_models if m.model_id == model_id)
        assert matched.is_rollback_override is False
    finally:
        _cleanup(registry_repo, training_run_repo, calibration_repo, model_id)


def test_active_model_reflects_rollback_override(service, registry_repo, training_run_repo, calibration_repo, rollback_repo):
    model_id = f"{_MODEL_ID_PREFIX}-active2"
    override_model_id = f"{_MODEL_ID_PREFIX}-override"
    engine_name = f"{_ENGINE_PREFIX}-active2"
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.XGBOOST, version="v1", label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.ACTIVE,
        engine_name=engine_name, engine_version="v1", artifact_path="/tmp/m.joblib",
    )
    registry_repo.save(entry)
    rollback_repo.set_override(LabelName.DIRECTION, 1, override_model_id, "test-admin")
    try:
        view = service.build()
        matched = next(m for m in view.active_models if m.label_name == "direction" and m.horizon_days == 1)
        assert matched.model_id == override_model_id
        assert matched.is_rollback_override is True
    finally:
        rollback_repo.clear_override(LabelName.DIRECTION, 1)
        _cleanup(registry_repo, training_run_repo, calibration_repo, model_id)


def test_shadow_models(service, registry_repo, training_run_repo, calibration_repo):
    model_id = f"{_MODEL_ID_PREFIX}-shadow"
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.CATBOOST, version="v1", label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.SHADOW,
        engine_name=f"{_ENGINE_PREFIX}-shadow", engine_version="v1", artifact_path="/tmp/m.joblib",
    )
    registry_repo.save(entry)
    try:
        view = service.build()
        assert any(m.model_id == model_id for m in view.shadow_models)
    finally:
        _cleanup(registry_repo, training_run_repo, calibration_repo, model_id)


def test_registry_entries_and_training_runs(service, registry_repo, training_run_repo, calibration_repo):
    model_id = f"{_MODEL_ID_PREFIX}-registry"
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
        engine_name=f"{_ENGINE_PREFIX}-registry", engine_version="v1", artifact_path="/tmp/m.joblib",
    )
    registry_repo.save(entry)
    run = TrainingRun(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, task_type=TaskType.CLASSIFICATION,
        label_name=LabelName.DIRECTION, horizon_days=1, status=TrainingRunStatus.COMPLETED,
        training_date=datetime.now(timezone.utc),
    )
    training_run_repo.save(run)
    try:
        view = service.build()
        assert any(r.model_id == model_id for r in view.registry_entries)
        assert any(r.model_id == model_id for r in view.training_runs)
    finally:
        _cleanup(registry_repo, training_run_repo, calibration_repo, model_id)


def test_promotion_history_marks_applied_when_active_registry_matches(service, promotion_repo, registry_repo, training_run_repo, calibration_repo):
    model_id = f"{_MODEL_ID_PREFIX}-promo"
    engine_name = f"{_ENGINE_PREFIX}-promo"
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.XGBOOST, version="v2", label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.ACTIVE,
        engine_name=engine_name, engine_version="v2", artifact_path="/tmp/m.joblib", promoted_at=datetime.now(timezone.utc),
    )
    registry_repo.save(entry)
    decision = PromotionDecision(
        engine_name=engine_name, candidate_version="v2", live_version="v1",
        recommendation=PromotionRecommendation.PROMOTE, rationale="better", window=RollingWindow.THIRTY_DAY,
        candidate_accuracy=0.9, live_accuracy=0.8, candidate_sample_count=50,
    )
    promotion_repo.save(decision)
    try:
        view = service.build()
        matched = next(p for p in view.promotion_history if p.engine_name == engine_name)
        assert matched.applied is True
        assert matched.applied_at is not None
    finally:
        conn = promotion_repo._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM research_promotion_decisions WHERE engine_name = %s", (engine_name,))
        finally:
            promotion_repo._pool.putconn(conn)
        _cleanup(registry_repo, training_run_repo, calibration_repo, model_id)


def test_promotion_history_not_applied_when_no_matching_active_registry(service, promotion_repo):
    engine_name = f"{_ENGINE_PREFIX}-promo-unapplied"
    decision = PromotionDecision(
        engine_name=engine_name, candidate_version="v2", live_version="v1",
        recommendation=PromotionRecommendation.KEEP_SHADOW, rationale="not yet", window=RollingWindow.THIRTY_DAY,
        candidate_accuracy=0.85, live_accuracy=0.86, candidate_sample_count=20,
    )
    promotion_repo.save(decision)
    try:
        view = service.build()
        matched = next(p for p in view.promotion_history if p.engine_name == engine_name)
        assert matched.applied is False
        assert matched.applied_at is None
    finally:
        conn = promotion_repo._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM research_promotion_decisions WHERE engine_name = %s", (engine_name,))
        finally:
            promotion_repo._pool.putconn(conn)


def test_benchmark_history(service, benchmark_repo):
    result = BenchmarkResult(
        subject_type=BenchmarkSubjectType.MODEL, subject_a=f"{_MODEL_ID_PREFIX}-bench-a",
        subject_b=f"{_MODEL_ID_PREFIX}-bench-b", window=RollingWindow.THIRTY_DAY, p_value=0.01, significant=True,
    )
    benchmark_repo.save(result)
    try:
        view = service.build()
        assert any(b.subject_a == f"{_MODEL_ID_PREFIX}-bench-a" for b in view.benchmark_history)
    finally:
        conn = benchmark_repo._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM research_benchmark_results WHERE subject_a = %s", (f"{_MODEL_ID_PREFIX}-bench-a",))
        finally:
            benchmark_repo._pool.putconn(conn)


def test_feature_importance_history(service, feature_store):
    model_id = f"{_MODEL_ID_PREFIX}-importance"
    feature_store.write_feature(FeatureValue(symbol=model_id, feature_name="shap_importance:rsi", value=0.42))
    try:
        view = service.build(feature_importance_model_ids=[model_id])
        assert any(f.model_id == model_id and f.feature_name == "rsi" and f.method == "shap" for f in view.feature_importance_history)
    finally:
        conn = feature_store.offline_store._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (model_id,))
        finally:
            feature_store.offline_store._pool.putconn(conn)


def test_feature_importance_history_empty_without_model_ids(service):
    view = service.build()
    assert view.feature_importance_history == []


# ─────────────────────────────────────────────────────────────────────────
# Feature Store failure resilience regression (production audit HIGH #7
# sweep - same "unguarded per-item Feature Store call" pattern as
# market_dashboard.py's HIGH #6 finding, found in the same package):
# _feature_importance_history's per-model_id/per-feature_name Feature
# Store calls had no try/except, so a Feature Store outage (or a single
# bad model_id) would crash the entire ML dashboard, not just feature
# importance history.
# ─────────────────────────────────────────────────────────────────────────

class _AlwaysFailingFeatureStore:
    def list_feature_names(self, symbol):
        raise RuntimeError("feature store unreachable")


class _PartiallyFailingFeatureStore:
    """Raises only for one specific model_id's list_feature_names call -
    proves per-model_id isolation, not just "happens not to raise"."""

    def __init__(self, failing_model_id: str, good_feature_store):
        self._failing_model_id = failing_model_id
        self._good = good_feature_store

    def list_feature_names(self, symbol):
        if symbol == self._failing_model_id:
            raise RuntimeError("feature store unreachable for this model")
        return self._good.list_feature_names(symbol)

    def get_feature_history(self, symbol, feature_name, start, end):
        return self._good.get_feature_history(symbol, feature_name, start, end)


def test_build_survives_a_feature_store_outage_during_importance_history(dashboard_repo):
    service = ModelDashboardService(dashboard_repo, feature_store=_AlwaysFailingFeatureStore())
    view = service.build(feature_importance_model_ids=["some-model"])  # must not raise
    assert view.feature_importance_history == []
    # the rest of the dashboard still comes through
    assert isinstance(view.registry_entries, list)


def test_build_excludes_only_the_model_whose_feature_store_lookup_fails(dashboard_repo, feature_store):
    good_model_id = f"{_MODEL_ID_PREFIX}-importance-good"
    bad_model_id = f"{_MODEL_ID_PREFIX}-importance-bad"
    feature_store.write_feature(FeatureValue(symbol=good_model_id, feature_name="shap_importance:rsi", value=0.42))

    service = ModelDashboardService(
        dashboard_repo, feature_store=_PartiallyFailingFeatureStore(bad_model_id, feature_store),
    )
    try:
        view = service.build(feature_importance_model_ids=[good_model_id, bad_model_id])  # must not raise
        model_ids_seen = {f.model_id for f in view.feature_importance_history}
        assert good_model_id in model_ids_seen
        assert bad_model_id not in model_ids_seen
    finally:
        conn = feature_store.offline_store._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (good_model_id,))
        finally:
            feature_store.offline_store._pool.putconn(conn)
