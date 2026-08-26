"""
Tests for the new /quant/analyze endpoint - the Quant Research
Platform's entry point into main.py. Real PostgreSQL/Redis/network/Groq,
matching this project's established testing philosophy.
"""
from decision_engine.repository import PostgresExecutionRepository
from feature_store.config import FeatureStoreConfig
from learning.persistence import LearningRepository

_SYMBOL = "AAPL"


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
