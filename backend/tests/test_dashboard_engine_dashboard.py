"""Tests for dashboard/engine_dashboard.py. Real PostgreSQL/Feature
Store throughout; a fake regime scanner keeps the regime-distribution
assertion deterministic without a live yfinance dependency."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from core.regime_scanner import MarketRegime, ScannedSymbol
from dashboard.engine_dashboard import EngineDashboardService
from dashboard.repository import DashboardRepository
from decision_engine.models import DecisionOutput, EngineVote, Prediction
from decision_engine.repository import PostgresExecutionRepository
from learning.config import LearningConfig
from learning.drift import DriftDetector
from learning.evaluator import OutcomeEvaluator
from learning.persistence import LearningRepository
from learning.scheduler import LearningScheduler
from learning.tracker import SampleTracker
from learning.weighting import WeightCalculator
from feature_store.service import FeatureStoreService

_ENGINE = "EngineDashTestEngine"
_SYMBOL = "ENGDASHX"


class _FakeRegimeScanner:
    def scan(self, symbols):
        return [ScannedSymbol(symbol=s, regime=MarketRegime.TRENDING_BULL, cumulative_return_pct=10.0, annualized_volatility_pct=15.0, trend_strength_r2=0.8, last_close=100.0) for s in symbols]


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
def service(dashboard_repo, learning_repo):
    return EngineDashboardService(dashboard_repo, learning_repository=learning_repo, regime_scanner=_FakeRegimeScanner())


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


def test_build_fetches_accuracy_in_one_batched_call_per_engine_not_one_per_window(service, learning_repo, monkeypatch):
    """Production audit MEDIUM #7: `_engine_snapshot` used to call
    `LearningService.get_accuracy` once per `RollingWindow` per engine
    (an O(engines x windows) query count). It must now call the
    batched `get_accuracy_for_windows` exactly once per engine, and
    never fall back to the old per-window method."""
    _seed_learning_cycle(learning_repo)
    try:
        batched_calls = []
        per_window_calls = []
        real_batched = service._learning_service.get_accuracy_for_windows
        real_per_window = service._learning_service.get_accuracy

        def _spy_batched(engine_name, engine_version, windows):
            batched_calls.append((engine_name, engine_version))
            return real_batched(engine_name, engine_version, windows)

        def _spy_per_window(*args, **kwargs):
            per_window_calls.append((args, kwargs))
            return real_per_window(*args, **kwargs)

        monkeypatch.setattr(service._learning_service, "get_accuracy_for_windows", _spy_batched)
        monkeypatch.setattr(service._learning_service, "get_accuracy", _spy_per_window)

        view = service.build()

        engine_count = len(view.engines)
        assert engine_count > 0
        assert len(batched_calls) == engine_count
        assert per_window_calls == []
    finally:
        _cleanup_learning(learning_repo)


def test_build_returns_engine_snapshots_with_accuracy_and_weight(service, learning_repo):
    _seed_learning_cycle(learning_repo)
    try:
        view = service.build()
        engine_names = {engine.engine_name for engine in view.engines}
        assert _ENGINE in engine_names
        snapshot = next(e for e in view.engines if e.engine_name == _ENGINE)
        assert snapshot.current_weight is not None
        assert len(snapshot.accuracy_by_window) > 0
    finally:
        _cleanup_learning(learning_repo)


def test_build_without_any_engines(dashboard_repo):
    empty_learning_repo = LearningRepository()
    service = EngineDashboardService(dashboard_repo, learning_repository=empty_learning_repo, regime_scanner=_FakeRegimeScanner())
    view = service.build()
    assert isinstance(view.engines, list)


def test_regime_distribution_uses_injected_scanner(service):
    view = service.build(regime_symbols=["AAPL", "MSFT"])
    assert view.regime_distribution == {"TRENDING_BULL": 2}


def test_regime_distribution_empty_without_symbols(service):
    view = service.build()
    assert view.regime_distribution == {}


def test_confidence_and_expected_return_history_from_real_executions(dashboard_repo, learning_repo):
    exec_repo = PostgresExecutionRepository()
    output = DecisionOutput(
        symbol="ENGDASH-EXEC-TEST", decision=Prediction.BUY, confidence=0.65, expected_return=3.0,
        expected_volatility=10.0, aggregation_strategy_version="test_v1", data_sufficiency=0.9, evidence=["e"],
        engine_results=[], timestamp=datetime.now(timezone.utc),
    )
    exec_repo.save(output)

    service = EngineDashboardService(dashboard_repo, learning_repository=learning_repo, regime_scanner=_FakeRegimeScanner())
    view = service.build(symbol="ENGDASH-EXEC-TEST")
    assert len(view.confidence_history) == 1
    assert view.confidence_history[0].value == pytest.approx(0.65)
    assert len(view.expected_return_history) == 1
    assert view.expected_return_history[0].value == pytest.approx(3.0)

    conn = exec_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM decision_engine_executions WHERE symbol = %s", ("ENGDASH-EXEC-TEST",))
    finally:
        exec_repo._pool.putconn(conn)
