"""Tests for research_lab/backtesting/."""
from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from learning.config import LearningConfig
from learning.evaluator import OutcomeEvaluator
from learning.persistence import LearningRepository
from learning.tracker import SampleTracker
from research_lab.backtesting import splitters
from research_lab.backtesting.engine import BacktestEngine
from research_lab.backtesting.repository import BacktestRepository
from research_lab.backtesting.service import BacktestService
from research_lab.config import ResearchLabConfig
from research_lab.models import BacktestMethod

import pandas as pd


def _series(n_days=200, start=None):
    start = start or (datetime.now(timezone.utc) - timedelta(days=n_days))
    return [(start + timedelta(days=i), 1.0 if i % 3 != 0 else -0.5) for i in range(n_days)]


# ─────────────────────────────────────────────────────────────────────────
# splitters.py (pure)
# ─────────────────────────────────────────────────────────────────────────

def test_walk_forward_splits_produces_nonoverlapping_folds():
    series = _series(200)
    folds = splitters.walk_forward_splits(series, train_window_days=90, test_window_days=30)
    assert len(folds) > 0
    for fold in folds:
        assert fold.test_start < fold.test_end


def test_walk_forward_splits_empty_series():
    assert splitters.walk_forward_splits([], 90, 30) == []


def test_rolling_window_splits_covers_series():
    series = _series(200)
    folds = splitters.rolling_window_splits(series, window_days=60, step_days=30)
    assert len(folds) > 0


def test_rolling_window_splits_empty_series():
    assert splitters.rolling_window_splits([], 60, 30) == []


def test_purged_cv_splits_produces_n_folds_with_embargo_gaps():
    series = _series(300)
    folds = splitters.purged_cv_splits(series, n_folds=5, embargo_days=2)
    assert len(folds) <= 5
    for i in range(len(folds) - 1):
        assert folds[i].test_end <= folds[i + 1].test_start


def test_purged_cv_splits_empty_series():
    assert splitters.purged_cv_splits([], 5, 2) == []


def test_stress_test_scenarios_applies_shock_to_every_period():
    series = [(datetime.now(timezone.utc), 5.0), (datetime.now(timezone.utc) + timedelta(days=1), 3.0)]
    folds = splitters.stress_test_scenarios(series, shock_pct=-10.0)
    assert len(folds) == 1
    assert [value for _, value in folds[0].test_series] == [-5.0, -7.0]


def test_out_of_sample_split_holds_out_most_recent_fraction():
    series = _series(100)
    folds = splitters.out_of_sample_split(series, holdout_ratio=0.2)
    assert len(folds) == 1
    assert len(folds[0].test_series) == pytest.approx(20, abs=1)


def test_out_of_sample_split_empty_series():
    assert splitters.out_of_sample_split([], 0.2) == []


def test_out_of_sample_split_with_zero_ratio_holds_out_nothing():
    series = _series(10)
    assert splitters.out_of_sample_split(series, holdout_ratio=0.0) == []


def test_purged_cv_splits_skips_folds_where_embargo_consumes_the_whole_span():
    series = _series(5)
    folds = splitters.purged_cv_splits(series, n_folds=20, embargo_days=30)
    assert folds == []


# ─────────────────────────────────────────────────────────────────────────
# engine.py
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method", list(BacktestMethod))
def test_backtest_engine_runs_every_method(method):
    series = _series(200)
    engine = BacktestEngine(config=ResearchLabConfig())
    result = engine.run(method, "TestEngine", "v1", series)
    assert result.method == method
    assert result.sample_count > 0
    assert result.window_start < result.window_end


def test_backtest_engine_filters_folds_below_minimum_sample_size():
    config = ResearchLabConfig(min_samples_for_backtest_fold=1000)
    engine = BacktestEngine(config=config)
    result = engine.run(BacktestMethod.WALK_FORWARD, "TestEngine", "v1", _series(200))
    assert result.folds == []
    assert result.sample_count == 0


def test_backtest_engine_stress_test_degrades_performance():
    series = _series(200)
    config = ResearchLabConfig(stress_test_shock_pct=-50.0)
    engine = BacktestEngine(config=config)
    result = engine.run(BacktestMethod.STRESS_TEST, "TestEngine", "v1", series)
    assert result.aggregate_expected_value < 0


def test_backtest_engine_with_empty_series():
    engine = BacktestEngine()
    result = engine.run(BacktestMethod.OUT_OF_SAMPLE, "TestEngine", "v1", [])
    assert result.sample_count == 0
    assert result.folds == []


# ─────────────────────────────────────────────────────────────────────────
# service.py (real Postgres, sourced from Continuous Learning)
# ─────────────────────────────────────────────────────────────────────────

_ENGINE = "BacktestSvcRealTest"
_SYMBOL = "BTSVCX"


@pytest.fixture
def learning_setup():
    repo = LearningRepository()
    config = LearningConfig(evaluation_horizon_days=5)
    tracker = SampleTracker(repository=repo, config=config)

    def fetcher(symbol, start, end):
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        return pd.DataFrame({"Close": [100 + i * 0.3 for i in range(len(dates))]}, index=dates)

    evaluator = OutcomeEvaluator(repository=repo, config=config, price_fetcher=fetcher)
    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    for i in range(10):
        vote = EngineVote(
            engine_name=_ENGINE, engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
            expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at - timedelta(days=i),
        )
        output = DecisionOutput(
            symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.7, expected_return=2.0,
            expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
            evidence=["e"], engine_results=[vote], timestamp=decided_at - timedelta(days=i),
        )
        tracker.track_decision(output)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    yield repo

    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def backtest_repository():
    repo = BacktestRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM research_backtest_results WHERE engine_name = %s", (_ENGINE,))
    finally:
        repo._pool.putconn(conn)


def test_backtest_service_sources_series_from_learning_and_persists(learning_setup, backtest_repository):
    config = ResearchLabConfig(min_samples_for_backtest_fold=1, out_of_sample_ratio=0.5)
    svc = BacktestService(learning_repository=learning_setup, repository=backtest_repository, config=config)
    result = svc.run(BacktestMethod.OUT_OF_SAMPLE, _ENGINE, "v1")
    assert result.id is not None
    assert result.sample_count > 0

    stored = backtest_repository.get(result.id)
    assert stored is not None
    assert stored.engine_name == _ENGINE


def test_backtest_service_defaults_to_real_dependencies():
    svc = BacktestService()
    assert isinstance(svc.learning_repository, LearningRepository)
    assert isinstance(svc.repository, BacktestRepository)


# ─────────────────────────────────────────────────────────────────────────
# repository.py read methods
# ─────────────────────────────────────────────────────────────────────────

def test_backtest_repository_get_round_trips(learning_setup, backtest_repository):
    config = ResearchLabConfig(min_samples_for_backtest_fold=1, out_of_sample_ratio=0.5)
    svc = BacktestService(learning_repository=learning_setup, repository=backtest_repository, config=config)
    result = svc.run(BacktestMethod.OUT_OF_SAMPLE, _ENGINE, "v1")
    fetched = backtest_repository.get(result.id)
    assert fetched is not None
    assert fetched.method == BacktestMethod.OUT_OF_SAMPLE


def test_backtest_repository_get_returns_none_for_unknown_id(backtest_repository):
    assert backtest_repository.get(999999999) is None


def test_backtest_repository_list_for_experiment(learning_setup, backtest_repository):
    config = ResearchLabConfig(min_samples_for_backtest_fold=1, out_of_sample_ratio=0.5)
    svc = BacktestService(learning_repository=learning_setup, repository=backtest_repository, config=config)
    result = svc.run(BacktestMethod.OUT_OF_SAMPLE, _ENGINE, "v1", experiment_id=42)
    results = backtest_repository.list_for_experiment(42)
    assert any(r.id == result.id for r in results)


def test_backtest_repository_list_for_engine(learning_setup, backtest_repository):
    config = ResearchLabConfig(min_samples_for_backtest_fold=1, out_of_sample_ratio=0.5)
    svc = BacktestService(learning_repository=learning_setup, repository=backtest_repository, config=config)
    svc.run(BacktestMethod.OUT_OF_SAMPLE, _ENGINE, "v1")
    results = backtest_repository.list_for_engine(_ENGINE, "v1")
    assert len(results) >= 1
    filtered = backtest_repository.list_for_engine(_ENGINE, "v1", method=BacktestMethod.OUT_OF_SAMPLE)
    assert all(r.method == BacktestMethod.OUT_OF_SAMPLE for r in filtered)
