"""Tests for learning/scheduler.py. Uses the real PostgreSQL-backed
LearningRepository and Feature Store, with a fake deterministic price
fetcher for the evaluator."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from feature_store.service import FeatureStoreService
from learning.config import LearningConfig
from learning.drift import DriftDetector
from learning.evaluator import OutcomeEvaluator
from learning.models import RollingWindow
from learning.persistence import LearningRepository
from learning.scheduler import LearningCycleResult, LearningScheduler
from learning.tracker import SampleTracker
from learning.weighting import WeightCalculator

_ENGINE = "SchedulerTestEngine"
_SYMBOL = "SCHEDX"


def _rising_price_fetcher(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    prices = [100 + i * 0.5 for i in range(len(dates))]
    return pd.DataFrame({"Close": prices}, index=dates)


@pytest.fixture
def scheduler_setup():
    repo = LearningRepository()
    feature_store = FeatureStoreService()
    config = LearningConfig(evaluation_horizon_days=5, min_samples_for_weighting=1, min_samples_for_drift=1)

    tracker = SampleTracker(repository=repo, config=config)
    evaluator = OutcomeEvaluator(repository=repo, config=config, price_fetcher=_rising_price_fetcher)
    weight_calculator = WeightCalculator(feature_store=feature_store, repository=repo, config=config)
    drift_detector = DriftDetector(config=config)
    scheduler = LearningScheduler(
        repository=repo, evaluator=evaluator, weight_calculator=weight_calculator,
        drift_detector=drift_detector, config=config,
    )

    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    for _ in range(3):
        vote = EngineVote(
            engine_name=_ENGINE, engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
            expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at,
        )
        output = DecisionOutput(
            symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.7, expected_return=2.0,
            expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
            evidence=["e"], engine_results=[vote], timestamp=decided_at,
        )
        tracker.track_decision(output)

    yield scheduler, repo, feature_store

    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
            cur.execute("DELETE FROM learning_accuracy_metrics WHERE engine_name = %s", (_ENGINE,))
            cur.execute("DELETE FROM learning_weight_updates WHERE engine_name = %s", (_ENGINE,))
            cur.execute("DELETE FROM learning_drift_signals WHERE engine_name = %s", (_ENGINE,))
    finally:
        repo._pool.putconn(conn)
    feature_store.online_store._client.delete(f"feature_store:{_ENGINE}:engine_accuracy_score")
    conn2 = feature_store.offline_store._pool.getconn()
    try:
        with conn2, conn2.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_ENGINE,))
    finally:
        feature_store.offline_store._pool.putconn(conn2)


def test_run_once_evaluates_matured_samples(scheduler_setup):
    scheduler, repo, _ = scheduler_setup
    result = scheduler.run_once(now=datetime.now(timezone.utc))
    assert isinstance(result, LearningCycleResult)
    assert result.evaluated_count == 3


def test_run_once_processes_the_observed_engine(scheduler_setup):
    scheduler, repo, _ = scheduler_setup
    result = scheduler.run_once(now=datetime.now(timezone.utc))
    assert result.engines_processed == 1
    assert (_ENGINE, "v1") in result.accuracy_snapshots


def test_run_once_computes_every_rolling_window(scheduler_setup):
    scheduler, repo, _ = scheduler_setup
    result = scheduler.run_once(now=datetime.now(timezone.utc))
    windows = set(result.accuracy_snapshots[(_ENGINE, "v1")].keys())
    assert windows == set(RollingWindow)


def test_run_once_produces_a_drift_signal_per_engine(scheduler_setup):
    scheduler, repo, _ = scheduler_setup
    result = scheduler.run_once(now=datetime.now(timezone.utc))
    assert len(result.drift_signals) == 1
    assert result.drift_signals[0].engine_name == _ENGINE


def test_run_once_produces_a_weight_update_per_engine(scheduler_setup):
    scheduler, repo, feature_store = scheduler_setup
    result = scheduler.run_once(now=datetime.now(timezone.utc))
    assert len(result.weight_updates) == 1
    record = feature_store.get_latest_feature(_ENGINE, "engine_accuracy_score")
    assert record is not None


def test_run_once_persists_accuracy_metrics_for_later_queries(scheduler_setup):
    scheduler, repo, _ = scheduler_setup
    scheduler.run_once(now=datetime.now(timezone.utc))
    latest = repo.get_latest_accuracy(_ENGINE, "v1", RollingWindow.LIFETIME)
    assert latest is not None
    assert latest.sample_count == 3


def test_run_once_is_idempotent_on_already_evaluated_samples(scheduler_setup):
    scheduler, repo, _ = scheduler_setup
    scheduler.run_once(now=datetime.now(timezone.utc))
    second = scheduler.run_once(now=datetime.now(timezone.utc))
    assert second.evaluated_count == 0


# ─────────────────────────────────────────────────────────────────────────
# Per-engine failure isolation regression (production audit HIGH #3:
# "Per-item loops are not individually protected. One bad sample/engine
# can abort an entire batch/cycle").
# ─────────────────────────────────────────────────────────────────────────

def test_one_failing_engine_does_not_abort_the_rest_of_the_cycle(scheduler_setup, monkeypatch):
    scheduler, repo, _ = scheduler_setup
    bad_engine = f"{_ENGINE}-BAD"

    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    tracker = SampleTracker(
        repository=repo, config=LearningConfig(evaluation_horizon_days=5, min_samples_for_weighting=1, min_samples_for_drift=1),
    )
    for _ in range(3):
        vote = EngineVote(
            engine_name=bad_engine, engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
            expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at,
        )
        output = DecisionOutput(
            symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.7, expected_return=2.0,
            expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
            evidence=["e"], engine_results=[vote], timestamp=decided_at,
        )
        tracker.track_decision(output)

    original_detect = scheduler.drift_detector.detect

    def _raise_for_bad_engine(engine_name, engine_version, metrics_by_window):
        if engine_name == bad_engine:
            raise RuntimeError("drift detector exploded")
        return original_detect(engine_name, engine_version, metrics_by_window)

    monkeypatch.setattr(scheduler.drift_detector, "detect", _raise_for_bad_engine)

    try:
        result = scheduler.run_once(now=datetime.now(timezone.utc))  # must not raise

        # The good engine (_ENGINE) still got fully processed even
        # though the bad one blew up mid-cycle.
        assert (_ENGINE, "v1") in result.accuracy_snapshots
        assert any(update.engine_name == _ENGINE for update in result.weight_updates)
        assert any(signal.engine_name == _ENGINE for signal in result.drift_signals)
        # The bad engine's own (failed) entries must not appear as if
        # they succeeded.
        assert all(signal.engine_name != bad_engine for signal in result.drift_signals)
        assert all(update.engine_name != bad_engine for update in result.weight_updates)
    finally:
        conn = repo._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM learning_accuracy_metrics WHERE engine_name = %s", (bad_engine,))
                cur.execute("DELETE FROM learning_weight_updates WHERE engine_name = %s", (bad_engine,))
                cur.execute("DELETE FROM learning_drift_signals WHERE engine_name = %s", (bad_engine,))
                cur.execute("DELETE FROM learning_engine_outcomes WHERE engine_name = %s", (bad_engine,))
        finally:
            repo._pool.putconn(conn)
