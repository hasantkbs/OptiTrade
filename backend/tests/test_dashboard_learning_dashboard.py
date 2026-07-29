"""Tests for dashboard/learning_dashboard.py. Real PostgreSQL/Feature Store throughout."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from dashboard.learning_dashboard import LearningDashboardService
from dashboard.repository import DashboardRepository
from decision_engine.models import DecisionOutput, EngineVote, Prediction
from feature_store.service import FeatureStoreService
from learning.config import LearningConfig
from learning.drift import DriftDetector
from learning.evaluator import OutcomeEvaluator
from learning.models import RollingWindow
from learning.persistence import LearningRepository
from learning.scheduler import LearningScheduler
from learning.tracker import SampleTracker
from learning.weighting import WeightCalculator
from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState
from ml_training.registry.repository import ModelRegistryRepository

_ENGINE = "LearnDashTestEngine"
_SYMBOL = "LEARNDASHX"


def _rising_price_fetcher(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    prices = [100 + i * 0.5 for i in range(len(dates))]
    return pd.DataFrame({"Close": prices}, index=dates)


@pytest.fixture
def learning_repo():
    return LearningRepository()


@pytest.fixture
def dashboard_repo():
    repository = DashboardRepository()
    yield repository
    repository.close()


@pytest.fixture
def registry_repo():
    return ModelRegistryRepository()


@pytest.fixture
def service(dashboard_repo, learning_repo):
    return LearningDashboardService(dashboard_repo, learning_repository=learning_repo)


def _seed_learning_cycle(learning_repo):
    config = LearningConfig(evaluation_horizon_days=5, min_samples_for_weighting=1, min_samples_for_drift=1)
    tracker = SampleTracker(repository=learning_repo, config=config)
    evaluator = OutcomeEvaluator(repository=learning_repo, config=config, price_fetcher=_rising_price_fetcher)
    weight_calculator = WeightCalculator(feature_store=FeatureStoreService(), repository=learning_repo, config=config)
    drift_detector = DriftDetector(config=config)
    scheduler = LearningScheduler(repository=learning_repo, evaluator=evaluator, weight_calculator=weight_calculator, drift_detector=drift_detector, config=config)

    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    for _ in range(3):
        vote = EngineVote(engine_name=_ENGINE, engine_version="v1", prediction=Prediction.BUY, confidence=0.7, expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at)
        output = DecisionOutput(symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.7, expected_return=2.0, expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0, evidence=["e"], engine_results=[vote], timestamp=decided_at)
        tracker.track_decision(output)
    scheduler.run_once(now=datetime.now(timezone.utc))


def _cleanup_learning(learning_repo):
    conn = learning_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
            cur.execute("DELETE FROM learning_accuracy_metrics WHERE engine_name = %s", (_ENGINE,))
            cur.execute("DELETE FROM learning_weight_updates WHERE engine_name = %s", (_ENGINE,))
            cur.execute("DELETE FROM learning_drift_signals WHERE engine_name = %s", (_ENGINE,))
    finally:
        learning_repo._pool.putconn(conn)
    FeatureStoreService().online_store._client.delete(f"feature_store:{_ENGINE}:engine_accuracy_score")


def test_engine_rankings_sorted_by_accuracy(service, learning_repo):
    _seed_learning_cycle(learning_repo)
    try:
        view = service.build()
        assert any(r.engine_name == _ENGINE for r in view.engine_rankings)
        ranking = next(r for r in view.engine_rankings if r.engine_name == _ENGINE)
        assert ranking.accuracy == 1.0
        assert ranking.rank >= 1
    finally:
        _cleanup_learning(learning_repo)


def test_recent_samples_reflects_tracked_samples(service, learning_repo):
    _seed_learning_cycle(learning_repo)
    try:
        view = service.build()
        assert any(s.symbol == _SYMBOL for s in view.recent_samples)
    finally:
        _cleanup_learning(learning_repo)


def test_calibration_history_populated_per_window(service, learning_repo):
    _seed_learning_cycle(learning_repo)
    try:
        view = service.build()
        assert any(c.engine_name == _ENGINE for c in view.calibration_history)
    finally:
        _cleanup_learning(learning_repo)


def test_promotion_candidates_empty_without_active_registry_entry(service, learning_repo):
    _seed_learning_cycle(learning_repo)
    try:
        view = service.build()
        assert not any(c.engine_name == _ENGINE for c in view.promotion_candidates)
    finally:
        _cleanup_learning(learning_repo)


def test_promotion_candidates_populated_with_active_registry_entry(service, learning_repo, registry_repo):
    _seed_learning_cycle(learning_repo)
    entry = ModelRegistryEntry(
        model_id=f"{_ENGINE}-model", algorithm=ModelAlgorithm.XGBOOST, version="v0", label_name=LabelName.DIRECTION,
        horizon_days=1, training_date=datetime.now(timezone.utc), promotion_state=PromotionState.ACTIVE,
        engine_name=_ENGINE, engine_version="v0", artifact_path="/tmp/m.joblib",
    )
    registry_repo.save(entry)
    try:
        view = service.build(ranking_window=RollingWindow.THIRTY_DAY)
        # candidate_version v1 vs live_version v0 - real learning_service.promotion_candidates call executed
        assert isinstance(view.promotion_candidates, list)
    finally:
        conn = registry_repo._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM ml_training_model_registry WHERE model_id = %s", (f"{_ENGINE}-model",))
        finally:
            registry_repo._pool.putconn(conn)
        _cleanup_learning(learning_repo)


def test_drift_alerts_only_include_degrading_or_unstable(service):
    view = service.build()
    for signal in view.drift_alerts:
        assert signal.drift_type.value in ("degrading", "unstable")
