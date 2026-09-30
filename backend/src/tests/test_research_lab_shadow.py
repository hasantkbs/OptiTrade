"""Tests for research_lab/shadow/. Uses the real PostgreSQL-backed
LearningRepository via LearningService."""
from datetime import datetime, timezone

import pytest

from decision_engine.models import EngineVote, Prediction
from learning.models import RollingWindow, SampleSource
from learning.persistence import LearningRepository
from learning.service import LearningService
from research_lab.shadow.service import ShadowEvaluationService

_ENGINE = "ShadowTestRealEngine"


class _FakeCandidateEngine:
    engine_name = _ENGINE
    engine_version = "v2"

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=Prediction.BUY, confidence=0.8, expected_return=2.0, volatility=15.0,
            evidence=["shadow evidence"],
        )


class _FailingEngine:
    engine_name = "FailingShadowEngine"
    engine_version = "v1"

    def vote(self, symbol: str):
        raise RuntimeError("simulated engine failure")


@pytest.fixture
def learning_service():
    repo = LearningRepository()
    svc = LearningService(repository=repo)
    yield svc
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM learning_samples WHERE id IN "
                "(SELECT sample_id FROM learning_engine_outcomes WHERE engine_name IN (%s, %s))",
                (_ENGINE, "FailingShadowEngine"),
            )
    finally:
        repo._pool.putconn(conn)


def test_run_shadow_pass_tracks_every_symbol_as_shadow(learning_service):
    svc = ShadowEvaluationService(learning_service=learning_service)
    samples = svc.run_shadow_pass(_FakeCandidateEngine(), ["AAPL", "MSFT"])
    assert len(samples) == 2
    assert all(sample.source == SampleSource.SHADOW for sample in samples)


def test_run_shadow_pass_skips_failing_symbols_without_raising(learning_service):
    svc = ShadowEvaluationService(learning_service=learning_service)
    samples = svc.run_shadow_pass(_FailingEngine(), ["AAPL"])
    assert samples == []


def test_compare_to_production_returns_both_sides(learning_service):
    svc = ShadowEvaluationService(learning_service=learning_service)
    shadow_metrics, live_metrics = svc.compare_to_production(_ENGINE, "v2", "v1", RollingWindow.LIFETIME)
    assert shadow_metrics is None  # no evaluated samples yet
    assert live_metrics is None


def test_service_defaults_to_real_learning_service():
    svc = ShadowEvaluationService()
    assert isinstance(svc.learning_service, LearningService)
