"""
Tests for dashboard/repository.py. Real PostgreSQL throughout. This
repository only reads tables owned by other packages, so each test
seeds real data through that owning package's own repository first
(never inserting raw rows dashboard doesn't own the schema for)."""
from datetime import datetime, timedelta, timezone

import pytest

from dashboard.repository import DashboardRepository
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
from research_lab.benchmarking.repository import BenchmarkRepository
from research_lab.models import BenchmarkResult, BenchmarkSubjectType, PromotionDecision, PromotionRecommendation
from research_lab.promotion.repository import PromotionRepository
from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.repository import WatchlistRepository

_MODEL_ID_PREFIX = "dash-repo-test-model"
_ENGINE_PREFIX = "dash-repo-test-engine"


@pytest.fixture
def repo():
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
def watchlist_repo():
    return WatchlistRepository()


def _cleanup_ml_training(registry_repo, training_run_repo, calibration_repo, model_id):
    conn = registry_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_model_registry WHERE model_id = %s", (model_id,))
    finally:
        registry_repo._pool.putconn(conn)
    conn = training_run_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_runs WHERE model_id = %s", (model_id,))
    finally:
        training_run_repo._pool.putconn(conn)
    conn = calibration_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_calibration_results WHERE model_id = %s", (model_id,))
    finally:
        calibration_repo._pool.putconn(conn)


def test_count_users_and_active_users(repo):
    assert repo.count_users() >= 0
    assert repo.count_active_users() >= 0


def test_count_portfolios_watchlists_alerts_paper_accounts(repo):
    assert repo.count_portfolios() >= 0
    assert repo.count_watchlists() >= 0
    assert repo.count_alerts() >= 0
    assert repo.count_paper_accounts() >= 0


def test_registry_entries_and_active_version_lookup(repo, registry_repo, training_run_repo, calibration_repo):
    model_id = f"{_MODEL_ID_PREFIX}-1"
    engine_name = f"{_ENGINE_PREFIX}-1"
    entry = ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.XGBOOST, version="v1", label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.ACTIVE,
        engine_name=engine_name, engine_version="v1", artifact_path="/tmp/model.joblib",
    )
    registry_repo.save(entry)

    before_count = repo.count_ml_models()
    entries = repo.list_registry_entries(promotion_state="active", limit=200)
    assert any(row["model_id"] == model_id for row in entries)
    assert repo.count_ml_models() == before_count

    fetched = repo.get_registry_entry(model_id)
    assert fetched["algorithm"] == "xgboost"

    active_version = repo.get_active_version_for_engine(engine_name)
    assert active_version == "v1"

    active_match = repo.find_active_registry_version(engine_name, "v1")
    assert active_match is not None
    assert active_match["model_id"] == model_id

    assert repo.find_active_registry_version(engine_name, "v999") is None
    assert repo.get_active_version_for_engine("nonexistent-engine") is None

    _cleanup_ml_training(registry_repo, training_run_repo, calibration_repo, model_id)


def test_training_runs(repo, training_run_repo, registry_repo, calibration_repo):
    model_id = f"{_MODEL_ID_PREFIX}-2"
    run = TrainingRun(
        model_id=model_id, algorithm=ModelAlgorithm.LIGHTGBM, task_type=TaskType.CLASSIFICATION,
        label_name=LabelName.DIRECTION, horizon_days=1, status=TrainingRunStatus.COMPLETED,
        training_date=datetime.now(timezone.utc),
    )
    training_run_repo.save(run)

    runs = repo.list_training_runs(limit=200)
    assert any(row["model_id"] == model_id for row in runs)
    _cleanup_ml_training(registry_repo, training_run_repo, calibration_repo, model_id)


def test_calibration_results(repo, calibration_repo, registry_repo, training_run_repo):
    model_id = f"{_MODEL_ID_PREFIX}-3"
    result = CalibrationResult(
        model_id=model_id, method=CalibrationMethod.ISOTONIC, calibration_error_before=0.2,
        calibration_error_after=0.05, artifact_path="/tmp/calibrator.joblib",
    )
    calibration_repo.save(result)

    all_results = repo.list_calibration_results(limit=200)
    assert any(row["model_id"] == model_id for row in all_results)
    scoped_results = repo.list_calibration_results(model_id=model_id)
    assert len(scoped_results) == 1
    assert scoped_results[0]["method"] == "isotonic"
    _cleanup_ml_training(registry_repo, training_run_repo, calibration_repo, model_id)


def test_benchmark_results(repo, benchmark_repo):
    result = BenchmarkResult(
        experiment_id=1, subject_type=BenchmarkSubjectType.MODEL, subject_a=f"{_MODEL_ID_PREFIX}-a",
        subject_b=f"{_MODEL_ID_PREFIX}-b", window=RollingWindow.THIRTY_DAY, metrics_a={"accuracy": 0.7},
        metrics_b={"accuracy": 0.8}, p_value=0.03, significant=True,
    )
    benchmark_repo.save(result)

    results = repo.list_benchmark_results(limit=200)
    assert any(row["subject_a"] == f"{_MODEL_ID_PREFIX}-a" for row in results)

    conn = benchmark_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM research_benchmark_results WHERE subject_a = %s", (f"{_MODEL_ID_PREFIX}-a",))
    finally:
        benchmark_repo._pool.putconn(conn)


def test_promotion_decisions(repo, promotion_repo):
    engine_name = f"{_ENGINE_PREFIX}-promo"
    decision = PromotionDecision(
        experiment_id=1, engine_name=engine_name, candidate_version="v2", live_version="v1",
        recommendation=PromotionRecommendation.PROMOTE, rationale="better accuracy", window=RollingWindow.THIRTY_DAY,
        candidate_accuracy=0.9, live_accuracy=0.8, candidate_sample_count=50,
    )
    promotion_repo.save(decision)

    all_decisions = repo.list_promotion_decisions(limit=200)
    assert any(row["engine_name"] == engine_name for row in all_decisions)
    scoped = repo.list_promotion_decisions(engine_name=engine_name)
    assert len(scoped) == 1
    assert scoped[0]["recommendation"] == "promote"

    conn = promotion_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM research_promotion_decisions WHERE engine_name = %s", (engine_name,))
    finally:
        promotion_repo._pool.putconn(conn)


def test_rollback_overrides_empty_by_default(repo):
    overrides = repo.list_rollback_overrides()
    assert isinstance(overrides, list)


def test_recent_decision_executions(repo):
    executions = repo.list_recent_decision_executions(limit=5)
    assert isinstance(executions, list)
    assert len(executions) <= 5


def test_alert_triggers_and_counts(repo, watchlist_repo):
    owner = "dash-repo-test-owner@example.com"
    alert = Alert(owner=owner, symbol="AAPL", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE, parameters={"threshold": 100.0})
    alert_id = watchlist_repo.save_alert(alert)
    now = datetime.now(timezone.utc)
    trigger_id = watchlist_repo.save_trigger(alert_id, now, "Price crossed above 100", {"price": 105.0})

    triggers = repo.list_alert_triggers(alert_id=alert_id)
    assert len(triggers) == 1
    assert triggers[0]["message"] == "Price crossed above 100"

    since_count = repo.count_alert_triggers_since(now - timedelta(minutes=5))
    assert since_count >= 1

    conn = watchlist_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM watchlist_alert_trigger_history WHERE id = %s", (trigger_id,))
            cur.execute("DELETE FROM watchlist_alerts WHERE id = %s", (alert_id,))
    finally:
        watchlist_repo._pool.putconn(conn)


def test_learning_sample_counts(repo):
    assert repo.count_learning_samples() >= 0
    assert repo.count_pending_learning_samples() >= 0
    assert isinstance(repo.list_recent_learning_samples(limit=5), list)


def test_ping(repo):
    assert repo.ping() is True
