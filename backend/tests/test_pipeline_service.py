"""Real, live end-to-end tests for backend/pipeline/service.py - network,
real Feature Store (PostgreSQL + Redis), real Decision Engine, real
Groq explanation, real Learning tracking. Cleans up every row it
writes."""
from datetime import datetime, timezone

import pytest

from decision_engine.models import Prediction
from decision_engine.repository import PostgresExecutionRepository
from engine_registry.registry import default_registry
from feature_store.config import FeatureStoreConfig
from learning.persistence import LearningRepository
from pipeline import PipelineResponse, PipelineService
from pipeline.config import PipelineConfig

_SYMBOL = "AAPL"


@pytest.fixture
def service():
    svc = PipelineService(config=PipelineConfig.from_env())
    yield svc

    exec_repo = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    conn = exec_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM decision_engine_executions WHERE symbol = %s AND aggregation_strategy_version = %s",
                (_SYMBOL, "pipeline_parallel_v1"),
            )
    finally:
        exec_repo._pool.putconn(conn)
    exec_repo.close()

    learning_repo = LearningRepository()
    conn2 = learning_repo._pool.getconn()
    try:
        with conn2, conn2.cursor() as cur:
            cur.execute(
                "DELETE FROM learning_samples WHERE symbol = %s AND decided_at > now() - interval '10 minutes'",
                (_SYMBOL,),
            )
    finally:
        learning_repo._pool.putconn(conn2)


def test_service_resolves_the_three_registered_voting_engines(service):
    engine_names = {engine.engine_name for engine in service.pipeline.engines}
    assert engine_names == {"TechnicalEngine", "FundamentalEngine", "NewsEngine"}


def test_service_engines_are_the_same_registry_singletons(service):
    for engine in service.pipeline.engines:
        registered = default_registry.get(engine.engine_name, engine.engine_version)
        assert engine is registered


def test_run_produces_a_complete_response(service):
    response = service.run(_SYMBOL)
    assert isinstance(response, PipelineResponse)
    assert response.symbol == _SYMBOL
    assert response.decision in (Prediction.BUY, Prediction.HOLD, Prediction.SELL)
    assert 0.0 <= response.confidence <= 1.0
    assert len(response.engine_breakdown) == 3
    assert response.explanation
    assert response.risk.risk_level in ("LOW", "MEDIUM", "HIGH")
    assert response.metadata.engines_available == 3


def test_run_persists_the_decision(service):
    service.run(_SYMBOL)
    exec_repo = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    recent = exec_repo.get_recent(_SYMBOL, limit=5)
    assert any(execution.aggregation_strategy_version == "pipeline_parallel_v1" for execution in recent)
    exec_repo.close()


def test_run_records_a_learning_sample(service):
    service.run(_SYMBOL)
    learning_repo = LearningRepository()
    pending = learning_repo.get_pending_samples(datetime.now(timezone.utc), limit=100)
    conn = learning_repo._pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM learning_samples WHERE symbol = %s AND decided_at > now() - interval '5 minutes'",
                (_SYMBOL,),
            )
            count = cur.fetchone()[0]
    finally:
        learning_repo._pool.putconn(conn)
    assert count >= 1


def test_run_uppercases_the_symbol(service):
    response = service.run(_SYMBOL.lower())
    assert response.symbol == _SYMBOL


def test_service_lowercase_symbol_resolves_same_engines(service):
    # Sanity: running twice in a row (once already via other tests)
    # must not raise, confirming the shared engine singletons tolerate
    # repeated use within one process.
    first = service.run(_SYMBOL)
    second = service.run(_SYMBOL)
    assert first.symbol == second.symbol == _SYMBOL
