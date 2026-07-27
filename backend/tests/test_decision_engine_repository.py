"""
Tests for decision_engine/repository.py, run against the real, local
PostgreSQL instance (same database as the Feature Store — see
feature_store.config.FeatureStoreConfig). Every test uses a unique,
randomly-suffixed test symbol and deletes its own rows in teardown.
"""
import uuid
from datetime import datetime, timezone

import pytest

from decision_engine.exceptions import ExecutionPersistenceError
from decision_engine.models import DecisionOutput, EngineVote, Prediction
from decision_engine.repository import PostgresExecutionRepository
from feature_store.config import FeatureStoreConfig


@pytest.fixture(scope="module")
def repo():
    r = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    yield r
    r.close()


@pytest.fixture
def symbol():
    return f"TEST-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def cleanup(repo, symbol):
    yield
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM decision_engine_executions WHERE symbol = %s", (symbol,))
    finally:
        repo._pool.putconn(conn)


def _output(symbol: str, decision=Prediction.BUY, confidence=0.7) -> DecisionOutput:
    vote = EngineVote(
        engine_name="TechnicalEngine", engine_version="v1", prediction=decision,
        confidence=confidence, expected_return=1.5, volatility=2.0, evidence=["RSI oversold"],
    )
    return DecisionOutput(
        symbol=symbol, decision=decision, confidence=confidence,
        expected_return=1.5, expected_volatility=2.0,
        aggregation_strategy_version="accuracy_weighted_v1",
        data_sufficiency=1.0, evidence=["TechnicalEngine: RSI oversold"],
        engine_results=[vote],
    )


def test_ping_succeeds_against_real_postgres(repo):
    assert repo.ping() is True


def test_schema_is_created_idempotently(repo):
    repo._init_schema()


def test_get_recent_returns_empty_list_when_nothing_stored(repo, symbol):
    assert repo.get_recent(symbol) == []


def test_save_then_get_recent_round_trips(repo, symbol):
    output = _output(symbol)
    repo.save(output)

    recent = repo.get_recent(symbol)
    assert len(recent) == 1
    fetched = recent[0]
    assert fetched.symbol == symbol
    assert fetched.decision == Prediction.BUY
    assert fetched.confidence == pytest.approx(0.7)
    assert fetched.expected_return == pytest.approx(1.5)
    assert fetched.expected_volatility == pytest.approx(2.0)
    assert fetched.data_sufficiency == pytest.approx(1.0)
    assert fetched.evidence == ["TechnicalEngine: RSI oversold"]
    assert len(fetched.engine_results) == 1
    assert fetched.engine_results[0].engine_name == "TechnicalEngine"
    assert fetched.engine_results[0].prediction == Prediction.BUY


def test_get_recent_orders_most_recent_first_and_respects_limit(repo, symbol):
    for decision in (Prediction.BUY, Prediction.HOLD, Prediction.SELL):
        repo.save(_output(symbol, decision=decision))

    recent = repo.get_recent(symbol, limit=2)
    assert len(recent) == 2
    # Most recently saved (SELL) must come first.
    assert recent[0].decision == Prediction.SELL
    assert recent[1].decision == Prediction.HOLD


def test_different_symbols_are_independent(repo, symbol):
    other_symbol = f"TEST-{uuid.uuid4().hex[:12]}"
    repo.save(_output(symbol, decision=Prediction.BUY))
    repo.save(_output(other_symbol, decision=Prediction.SELL))
    try:
        assert repo.get_recent(symbol)[0].decision == Prediction.BUY
        assert repo.get_recent(other_symbol)[0].decision == Prediction.SELL
    finally:
        conn = repo._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM decision_engine_executions WHERE symbol = %s", (other_symbol,))
        finally:
            repo._pool.putconn(conn)


def test_save_wraps_a_real_database_error_in_executionpersistenceerror(repo, symbol):
    repo._pool.closeall()
    try:
        with pytest.raises(ExecutionPersistenceError):
            repo.save(_output(symbol))
    finally:
        repo._pool = repo._pool.__class__(
            1, 5,
            host=repo._config.postgres_host, port=repo._config.postgres_port,
            dbname=repo._config.postgres_db, user=repo._config.postgres_user,
            password=repo._config.postgres_password,
        )


def test_get_recent_wraps_a_real_database_error_in_executionpersistenceerror(repo, symbol):
    repo._pool.closeall()
    try:
        with pytest.raises(ExecutionPersistenceError):
            repo.get_recent(symbol)
    finally:
        repo._pool = repo._pool.__class__(
            1, 5,
            host=repo._config.postgres_host, port=repo._config.postgres_port,
            dbname=repo._config.postgres_db, user=repo._config.postgres_user,
            password=repo._config.postgres_password,
        )
