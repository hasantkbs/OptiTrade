"""
Tests for the new /quant/analyze endpoint - the Quant Research
Platform's entry point into main.py. Real PostgreSQL/Redis/network/Groq,
matching this project's established testing philosophy.
"""
import pytest

from decision_engine.repository import PostgresExecutionRepository
from feature_store.config import FeatureStoreConfig
from learning.persistence import LearningRepository

_SYMBOL = "AAPL"


@pytest.fixture(autouse=True)
def _clear_quant_analyze_cache():
    """_QUANT_ANALYZE_CACHE is a module-level singleton (main.py) shared
    across every test in the process, not per-client-fixture state - left
    uncleared, a cache entry from one test would silently turn every
    later test in this file into a cache-hit passthrough that never
    exercises the real pipeline, defeating what these tests are actually
    meant to check (and leaving _cleanup() below with nothing to delete).
    The dedicated caching tests further down clear it themselves at the
    point they need an empty cache, same as this fixture does for every
    other test."""
    import main

    main._QUANT_ANALYZE_CACHE.clear()
    yield
    main._QUANT_ANALYZE_CACHE.clear()


def _cleanup(symbol: str) -> None:
    exec_repo = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    conn = exec_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM decision_engine_executions WHERE symbol = %s AND aggregation_strategy_version = %s",
                (symbol, "pipeline_parallel_v1"),
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
                (symbol,),
            )
    finally:
        learning_repo._pool.putconn(conn2)


def test_quant_analyze_returns_the_full_new_schema(client):
    response = client.post("/quant/analyze", json={"symbol": _SYMBOL, "asset_type": "stock"})
    assert response.status_code == 200
    body = response.json()

    for field in (
        "symbol", "decision", "confidence", "expected_return", "expected_volatility",
        "engine_breakdown", "evidence", "risk", "explanation", "metadata",
    ):
        assert field in body, f"missing field: {field}"

    assert body["symbol"] == _SYMBOL
    assert body["decision"] in ("BUY", "HOLD", "SELL")
    assert 0.0 <= body["confidence"] <= 1.0
    assert len(body["engine_breakdown"]) == 3
    assert isinstance(body["evidence"], list)
    assert set(body["risk"].keys()) >= {"risk_level", "expected_volatility", "data_sufficiency"}
    assert isinstance(body["explanation"], str) and len(body["explanation"]) > 0
    assert set(body["metadata"].keys()) >= {
        "pipeline_version", "total_duration_ms", "stage_durations_ms",
        "engines_available", "engines_succeeded", "degraded", "timestamp",
    }

    _cleanup(_SYMBOL)


def test_quant_analyze_engine_breakdown_has_three_named_engines(client):
    response = client.post("/quant/analyze", json={"symbol": _SYMBOL})
    body = response.json()
    engine_names = {item["engine_name"] for item in body["engine_breakdown"]}
    assert engine_names == {"TechnicalEngine", "FundamentalEngine", "NewsEngine"}
    _cleanup(_SYMBOL)


def test_quant_analyze_symbol_is_uppercased(client):
    response = client.post("/quant/analyze", json={"symbol": _SYMBOL.lower()})
    assert response.status_code == 200
    assert response.json()["symbol"] == _SYMBOL
    _cleanup(_SYMBOL)


def test_quant_analyze_missing_symbol_returns_422(client):
    response = client.post("/quant/analyze", json={"asset_type": "stock"})
    assert response.status_code == 422


def test_quant_analyze_returns_503_when_pipeline_not_ready(client):
    import main

    original = main._pipeline_service
    main._pipeline_service = None
    try:
        response = client.post("/quant/analyze", json={"symbol": _SYMBOL})
        assert response.status_code == 503
    finally:
        main._pipeline_service = original


def test_quant_analyze_default_asset_type_is_stock(client):
    response = client.post("/quant/analyze", json={"symbol": _SYMBOL})
    assert response.status_code == 200
    _cleanup(_SYMBOL)


# ─────────────────────────────────────────────────────────────────────────
# _QUANT_ANALYZE_CACHE (performance fix): a cold symbol's Fundamental
# engine call alone has been observed taking 20-38s, well past both the
# frontend's own request timeout and nginx's 30s proxy_read_timeout -
# this cache means a retry (or any other request for the same symbol
# shortly after) gets the result that kept computing server-side instead
# of recomputing from scratch. `main._pipeline_service` is swapped for a
# fake here (same technique test_quant_analyze_returns_503_when_pipeline_
# not_ready above already uses) because these tests are about main.py's
# own caching logic, not the real pipeline's substance.
# ─────────────────────────────────────────────────────────────────────────

def _fake_pipeline_response(symbol: str) -> dict:
    return {
        "symbol": symbol, "decision": "HOLD", "confidence": 0.5,
        "expected_return": 0.0, "expected_volatility": 0.1,
        "engine_breakdown": [], "evidence": [],
        "risk": {"risk_level": "MEDIUM", "expected_volatility": 0.1, "data_sufficiency": 0.5},
        "explanation": "fake", "metadata": {
            "pipeline_version": "test", "total_duration_ms": 1.0, "stage_durations_ms": {},
            "engines_available": 3, "engines_succeeded": 3, "degraded": False,
            "timestamp": "2026-01-01T00:00:00Z",
        },
    }


def test_quant_analyze_caches_a_successful_result_and_skips_a_second_pipeline_run(client):
    import main

    calls = []

    class _FakePipelineService:
        def run(self, symbol):
            calls.append(symbol)
            return _fake_pipeline_response(symbol)

    original = main._pipeline_service
    main._pipeline_service = _FakePipelineService()
    try:
        first = client.post("/quant/analyze", json={"symbol": "ZZZZ"})
        second = client.post("/quant/analyze", json={"symbol": "ZZZZ"})
    finally:
        main._pipeline_service = original

    assert first.status_code == 200 and second.status_code == 200
    assert calls == ["ZZZZ"]  # second call was a cache hit, not a second pipeline run
    assert first.json() == second.json()


def test_quant_analyze_cache_is_keyed_per_symbol(client):
    import main

    calls = []

    class _FakePipelineService:
        def run(self, symbol):
            calls.append(symbol)
            return _fake_pipeline_response(symbol)

    original = main._pipeline_service
    main._pipeline_service = _FakePipelineService()
    try:
        client.post("/quant/analyze", json={"symbol": "YYYY"})
        client.post("/quant/analyze", json={"symbol": "XXXX"})
    finally:
        main._pipeline_service = original

    assert calls == ["YYYY", "XXXX"]
