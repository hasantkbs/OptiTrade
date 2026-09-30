"""Tests for learning/tracker.py. Uses the real PostgreSQL-backed
LearningRepository."""
from datetime import datetime, timezone

import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from learning.config import LearningConfig
from learning.models import SampleSource
from learning.persistence import LearningRepository
from learning.tracker import SampleTracker

_SYMBOL = "TRACKX"


@pytest.fixture
def tracker():
    repo = LearningRepository()
    config = LearningConfig(evaluation_horizon_days=5)
    yield SampleTracker(repository=repo, config=config)
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
    finally:
        repo._pool.putconn(conn)


def _vote() -> EngineVote:
    return EngineVote(
        engine_name="TrackerTestEngine", engine_version="v1", prediction=Prediction.BUY,
        confidence=0.8, expected_return=3.0, volatility=15.0, evidence=["headline evidence"],
    )


def test_track_decision_persists_a_sample_with_an_id(tracker):
    output = DecisionOutput(
        symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.8, expected_return=3.0,
        expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
        evidence=["e"], engine_results=[_vote()], timestamp=datetime.now(timezone.utc),
    )
    sample = tracker.track_decision(output)
    assert sample.id is not None
    assert sample.source == SampleSource.LIVE
    assert sample.symbol == _SYMBOL
    assert sample.evaluation_horizon_days == 5


def test_track_decision_persists_engine_outcomes(tracker):
    output = DecisionOutput(
        symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.8, expected_return=3.0,
        expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
        evidence=["e"], engine_results=[_vote()], timestamp=datetime.now(timezone.utc),
    )
    sample = tracker.track_decision(output)
    outcomes = tracker.repository.get_engine_outcomes(
        "TrackerTestEngine", "v1", since=datetime.now(timezone.utc).replace(year=2000), only_evaluated=False,
    )
    assert any(o.sample_id == sample.id for o in outcomes)


def test_track_shadow_vote_calls_engine_and_persists_as_shadow(tracker):
    class FakeShadowEngine:
        engine_name = "ShadowTestEngine"
        engine_version = "v2"

        def vote(self, symbol: str) -> EngineVote:
            return EngineVote(
                engine_name=self.engine_name, engine_version=self.engine_version,
                prediction=Prediction.SELL, confidence=0.6, expected_return=-2.0,
                volatility=18.0, evidence=["shadow evidence"],
            )

    sample = tracker.track_shadow_vote(FakeShadowEngine(), _SYMBOL)
    assert sample.source == SampleSource.SHADOW
    assert sample.decision == Prediction.SELL
    assert len(sample.engine_results) == 1
    assert sample.engine_results[0].engine_name == "ShadowTestEngine"

    conn = tracker.repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_engine_outcomes WHERE engine_name = 'ShadowTestEngine'")
    finally:
        tracker.repository._pool.putconn(conn)


def test_track_decision_defaults_to_real_repository_and_config():
    tracker = SampleTracker()
    assert isinstance(tracker.repository, LearningRepository)
    assert isinstance(tracker.config, LearningConfig)
