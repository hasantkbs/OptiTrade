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
    other test.

    Also resets main.limiter (slowapi) before each test: conftest.py's
    `client` fixture is module-scoped and already resets it once per
    module, but /quant/analyze is capped at 10/minute and this file alone
    now runs more than 10 real requests against it - without a per-test
    reset too, tests later in the file get a real 429 instead of 200
    purely from earlier tests in the same file spending the shared quota,
    not from anything the test itself is checking."""
    import main

    main.limiter.reset()
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


def test_quant_analyze_populates_chart_ai_for_a_supported_symbol(client):
    """AAPL is live in ml.chart_model.get_supported_symbols() as of
    2026-10-22 (docs/btc-chart-model-training-2026-10-22.md). If this
    ever changes, pick another symbol from that doc's live list
    instead of weakening this test."""
    response = client.post("/quant/analyze", json={"symbol": "AAPL"})
    assert response.status_code == 200
    chart_ai = response.json()["chart_ai"]
    assert chart_ai is not None
    assert chart_ai["signal"] in ("BUY", "SELL", "NEUTRAL")
    assert 0.0 <= chart_ai["confidence"] <= 1.0
    _cleanup("AAPL")


def test_quant_analyze_chart_ai_is_none_for_an_unsupported_symbol(client):
    """MSFT was trained but excluded from SUPPORTED_SYMBOLS (window 2
    failed significance - docs/btc-chart-model-training-2026-10-22.md)
    - a real symbol with a real decision_engine result, just no live
    chart-AI model."""
    response = client.post("/quant/analyze", json={"symbol": "MSFT"})
    assert response.status_code == 200
    assert response.json()["chart_ai"] is None
    _cleanup("MSFT")


def test_quant_analyze_chart_ai_failure_does_not_break_the_request(client, monkeypatch):
    import yfinance as yf

    def _raise(self, period=None):
        raise RuntimeError("yfinance unavailable")

    monkeypatch.setattr(yf.Ticker, "history", _raise)

    response = client.post("/quant/analyze", json={"symbol": "AAPL"})
    assert response.status_code == 200
    assert response.json()["chart_ai"] is None
    _cleanup("AAPL")


def test_quant_analyze_chart_ai_stays_none_when_history_is_too_short(client, monkeypatch):
    """predict_chart_signal() (ml/chart_model.py) returns {"signal": None,
    "error": "..."} - not an exception - when it gets real but insufficient
    history (fewer than WINDOW=60 rows). _attach_chart_ai's own
    `chart_ai_result.get("signal")` check must treat that the same as "no
    model": chart_ai stays None and the error string must never reach a
    response field a user sees. Distinct from
    test_quant_analyze_chart_ai_failure_does_not_break_the_request above,
    which only exercises the `except Exception` branch (history() raising),
    not this real-return-value branch."""
    import yfinance as yf

    real_history = yf.Ticker.history

    def _too_short(self, period=None):
        return real_history(self, period=period).tail(20)

    monkeypatch.setattr(yf.Ticker, "history", _too_short)

    response = client.post("/quant/analyze", json={"symbol": "AAPL"})
    assert response.status_code == 200
    assert response.json()["chart_ai"] is None
    assert "Yetersiz" not in response.text
    _cleanup("AAPL")


def test_quant_analyze_does_not_block_other_requests_while_attaching_chart_ai(client, monkeypatch):
    """_attach_chart_ai does a blocking yfinance call plus a Keras predict.
    quant_analyze is `async def` and already runs the real pipeline via
    run_in_executor for exactly this reason - if _attach_chart_ai were ever
    called directly on the event-loop thread instead, every other
    coroutine on this worker (including an unrelated concurrent
    /quant/analyze request) would stall for its whole duration. Uses the
    file's own _fake_pipeline_response (already used by the caching tests
    above) so this test exercises only the event-loop-blocking behavior,
    not real network/DB speed."""
    import asyncio
    import time

    import httpx

    import main

    class _FakePipelineService:
        def run(self, symbol):
            return _fake_pipeline_response(symbol)

    def _slow_only_for_the_slow_symbol(result):
        # _fake_pipeline_response (above) returns a plain dict, same as
        # the pre-existing caching tests already rely on - not a real
        # PipelineResponse, so index rather than attribute-access it.
        if result["symbol"] == "SLOWCHARTAI":
            time.sleep(0.5)

    original_pipeline = main._pipeline_service
    main._pipeline_service = _FakePipelineService()
    monkeypatch.setattr(main, "_attach_chart_ai", _slow_only_for_the_slow_symbol)

    async def _run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            # Both requests start from the same timer baseline, with the
            # slow one created first - if _attach_chart_ai runs
            # synchronously on the event loop thread, the fast task
            # literally cannot be resumed until the slow one's blocking
            # sleep returns, however fast attaching chart_ai is for the
            # fast symbol itself.
            start = time.monotonic()
            slow_task = asyncio.create_task(ac.post("/quant/analyze", json={"symbol": "SLOWCHARTAI"}))
            fast_task = asyncio.create_task(ac.post("/quant/analyze", json={"symbol": "FASTCHARTAI"}))
            fast_response = await fast_task
            fast_elapsed = time.monotonic() - start
            await slow_task
            return fast_response, fast_elapsed

    try:
        fast_response, fast_elapsed = asyncio.run(_run())
    finally:
        main._pipeline_service = original_pipeline

    assert fast_response.status_code == 200
    # Well under the slow call's 0.5s sleep - proves the event loop kept
    # serving other requests instead of blocking on _attach_chart_ai.
    assert fast_elapsed < 0.3
