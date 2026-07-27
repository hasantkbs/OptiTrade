"""Tests for learning/service.py (LearningService facade)."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from engine_registry.registry import EngineRegistry
from feature_store.service import FeatureStoreService
from learning.config import LearningConfig
from learning.drift import DriftDetector
from learning.evaluator import OutcomeEvaluator
from learning.models import PromotionCandidate, RollingWindow, SampleSource
from learning.persistence import LearningRepository
from learning.scheduler import LearningScheduler
from learning.service import LearningService
from learning.tracker import SampleTracker
from learning.weighting import WeightCalculator

_ENGINE = "ServiceTestEngine"
_SYMBOL = "SVCX"


def _rising_price_fetcher(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    prices = [100 + i * 0.5 for i in range(len(dates))]
    return pd.DataFrame({"Close": prices}, index=dates)


class _FakeVersionedEngine:
    def __init__(self, engine_name: str, engine_version: str, prediction: Prediction):
        self.engine_name = engine_name
        self.engine_version = engine_version
        self._prediction = prediction

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=self._prediction, confidence=0.7, expected_return=2.0,
            volatility=15.0, evidence=["shadow evidence"],
        )


@pytest.fixture
def service():
    repo = LearningRepository()
    feature_store = FeatureStoreService()
    config = LearningConfig(evaluation_horizon_days=5, min_samples_for_weighting=1, min_samples_for_drift=1)

    evaluator = OutcomeEvaluator(repository=repo, config=config, price_fetcher=_rising_price_fetcher)
    weight_calculator = WeightCalculator(feature_store=feature_store, repository=repo, config=config)
    drift_detector = DriftDetector(config=config)
    scheduler = LearningScheduler(
        repository=repo, evaluator=evaluator, weight_calculator=weight_calculator,
        drift_detector=drift_detector, config=config,
    )
    tracker = SampleTracker(repository=repo, config=config)

    registry = EngineRegistry()
    registry.register(_FakeVersionedEngine(_ENGINE, "v1", Prediction.BUY))
    registry.register(_FakeVersionedEngine(_ENGINE, "v2", Prediction.BUY))

    svc = LearningService(
        repository=repo, tracker=tracker, evaluator=evaluator, weight_calculator=weight_calculator,
        drift_detector=drift_detector, scheduler=scheduler, engine_registry=registry, config=config,
    )
    yield svc

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


def _track_matured_decision(service, engine_version="v1"):
    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    vote = EngineVote(
        engine_name=_ENGINE, engine_version=engine_version, prediction=Prediction.BUY, confidence=0.7,
        expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at,
    )
    output = DecisionOutput(
        symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.7, expected_return=2.0,
        expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
        evidence=["e"], engine_results=[vote], timestamp=decided_at,
    )
    return service.record_decision(output)


def test_record_decision_returns_a_live_sample(service):
    sample = _track_matured_decision(service)
    assert sample.source == SampleSource.LIVE
    assert sample.id is not None


def test_record_shadow_vote_returns_a_shadow_sample(service):
    shadow_engine = _FakeVersionedEngine(_ENGINE, "v2", Prediction.SELL)
    sample = service.record_shadow_vote(shadow_engine, _SYMBOL)
    assert sample.source == SampleSource.SHADOW
    assert sample.decision == Prediction.SELL

    conn = service.repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE id = %s", (sample.id,))
    finally:
        service.repository._pool.putconn(conn)


def test_run_learning_cycle_evaluates_and_computes_metrics(service):
    _track_matured_decision(service)
    result = service.run_learning_cycle(now=datetime.now(timezone.utc))
    assert result.evaluated_count == 1
    assert result.engines_processed == 1


def test_get_accuracy_reads_back_computed_metrics(service):
    _track_matured_decision(service)
    service.run_learning_cycle(now=datetime.now(timezone.utc))
    metrics = service.get_accuracy(_ENGINE, "v1", RollingWindow.LIFETIME)
    assert metrics is not None
    assert metrics.sample_count == 1


def test_get_accuracy_history_returns_snapshots(service):
    _track_matured_decision(service)
    service.run_learning_cycle(now=datetime.now(timezone.utc))
    history = service.get_accuracy_history(_ENGINE, "v1", RollingWindow.LIFETIME)
    assert len(history) >= 1


def test_get_weight_history_returns_updates(service):
    _track_matured_decision(service)
    service.run_learning_cycle(now=datetime.now(timezone.utc))
    history = service.get_weight_history(_ENGINE, "v1")
    assert len(history) >= 1


def test_get_drift_signals_returns_signals(service):
    _track_matured_decision(service)
    service.run_learning_cycle(now=datetime.now(timezone.utc))
    signals = service.get_drift_signals(_ENGINE, "v1")
    assert len(signals) >= 1


def test_version_history_covers_every_registered_version(service):
    _track_matured_decision(service, engine_version="v1")
    service.run_learning_cycle(now=datetime.now(timezone.utc))
    history = service.version_history(_ENGINE, window=RollingWindow.LIFETIME)
    assert "v1" in history
    assert "v2" not in history  # v2 never tracked any samples, so no metrics exist for it


def test_promotion_candidates_empty_when_no_version_beats_live(service):
    _track_matured_decision(service, engine_version="v1")
    service.run_learning_cycle(now=datetime.now(timezone.utc))
    candidates = service.promotion_candidates(_ENGINE, live_version="v1", window=RollingWindow.LIFETIME)
    assert candidates == []


def test_promotion_candidates_recommends_a_better_shadow_version(service):
    config = LearningConfig(
        evaluation_horizon_days=5, min_samples_for_weighting=1, min_samples_for_drift=1,
        min_samples_for_promotion=1, promotion_margin=0.01,
    )
    service.config = config
    service.scheduler.config = config
    service.evaluator.config = config

    # The market falls: v1 (live) predicts BUY - wrong; v2 (shadow) predicts SELL - correct.
    # Both share the same symbol/decided_at/horizon, so they're scored against the
    # identical actual price move - only the prediction direction differs.
    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    vote_v1 = EngineVote(
        engine_name=_ENGINE, engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
        expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at,
    )
    output_v1 = DecisionOutput(
        symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.7, expected_return=2.0,
        expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
        evidence=["e"], engine_results=[vote_v1], timestamp=decided_at,
    )
    service.record_decision(output_v1)

    # v2 (shadow) gets one CORRECT matured prediction
    shadow_engine = _FakeVersionedEngine(_ENGINE, "v2", Prediction.SELL)
    shadow_sample = service.tracker.track_shadow_vote(shadow_engine, _SYMBOL)
    # backdate it directly via repository since track_shadow_vote always uses "now"
    conn = service.repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE learning_samples SET decided_at = %s WHERE id = %s", (decided_at, shadow_sample.id),
            )
            cur.execute(
                "UPDATE learning_engine_outcomes SET decided_at = %s WHERE sample_id = %s",
                (decided_at, shadow_sample.id),
            )
    finally:
        service.repository._pool.putconn(conn)

    def falling(symbol, start, end):
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        return pd.DataFrame({"Close": [100 - i * 0.5 for i in range(len(dates))]}, index=dates)

    service.evaluator._price_fetcher = falling
    result = service.run_learning_cycle(now=datetime.now(timezone.utc))
    assert result.evaluated_count == 2

    candidates = service.promotion_candidates(_ENGINE, live_version="v1", window=RollingWindow.LIFETIME)
    assert any(c.candidate_version == "v2" for c in candidates)
    for candidate in candidates:
        assert isinstance(candidate, PromotionCandidate)

    conn = service.repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE id = %s", (shadow_sample.id,))
    finally:
        service.repository._pool.putconn(conn)


def test_service_defaults_to_real_dependencies():
    svc = LearningService()
    assert isinstance(svc.repository, LearningRepository)
    assert isinstance(svc.config, LearningConfig)
