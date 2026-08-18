"""
Tests for v2/api/router.py and v2/core/backtest_engine.py (production
audit MEDIUM #8): both used to call yfinance's synchronous
`Ticker(...).history(...)` directly inside `async def` routes/
functions, blocking the whole event loop - and therefore every other
concurrent request - for as long as the network call took. Every
blocking fetch is now dispatched via `asyncio.to_thread`, the same
pattern `model_serving/inference.py`/`model_serving/service.py`
already use for their own blocking calls.

These tests prove the fix by running a fake, artificially slow fetch
concurrently with a fast "heartbeat" coroutine: if the fetch still ran
on the event-loop thread, the heartbeat would be starved for the whole
sleep duration; dispatched via `asyncio.to_thread`, the heartbeat keeps
ticking while the fetch is "in flight" on a worker thread.
"""
import asyncio
import time

import pandas as pd
import pytest
from fastapi import HTTPException

import v2.api.router as v2_router
import v2.core.backtest_engine as v2_backtest


def _ohlcv(rows: int = 60) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0] * rows, "High": [101.0] * rows,
            "Low": [99.0] * rows, "Close": [100.0 + i * 0.01 for i in range(rows)],
            "Volume": [1000.0] * rows,
        },
        index=index,
    )


async def _count_heartbeats_during(coro, interval: float = 0.01) -> int:
    """Runs `coro` to completion while counting how many times a
    concurrent, cheap coroutine gets scheduled - a proxy for "was the
    event loop free to do other work while this ran"."""
    heartbeats = 0
    stop = False

    async def _heartbeat():
        nonlocal heartbeats
        while not stop:
            heartbeats += 1
            await asyncio.sleep(interval)

    heartbeat_task = asyncio.ensure_future(_heartbeat())
    try:
        await coro
    finally:
        stop = True
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
    return heartbeats


@pytest.mark.asyncio
async def test_analyze_symbol_does_not_block_the_event_loop(monkeypatch):
    def _slow_fetch(symbol, period, interval):
        time.sleep(0.3)  # simulates a slow, real yfinance network call
        return _ohlcv()

    monkeypatch.setattr(v2_router, "_fetch_history", _slow_fetch)

    heartbeats = await _count_heartbeats_during(
        v2_router.analyze_symbol("AAPL", period="60d", interval="1h"), interval=0.02,
    )
    # A 0.3s blocking sleep dispatched off-thread leaves plenty of room
    # for a 0.02s-interval heartbeat to tick many times; if the fetch
    # ran on the event loop instead, the heartbeat would be starved and
    # this would be 0 or 1.
    assert heartbeats >= 5


@pytest.mark.asyncio
async def test_analyze_symbol_response_is_unaffected_by_the_dispatch_change(monkeypatch):
    monkeypatch.setattr(v2_router, "_fetch_history", lambda symbol, period, interval: _ohlcv())

    result = await v2_router.analyze_symbol("AAPL", period="60d", interval="1h")
    assert result.symbol == "AAPL"
    assert result.signals


@pytest.mark.asyncio
async def test_analyze_symbol_retries_the_original_symbol_when_resolved_symbol_has_no_data(monkeypatch):
    calls = []

    def _fetch(symbol, period, interval):
        calls.append(symbol)
        if symbol == "BTC-USD":
            return pd.DataFrame()  # resolved symbol has no data
        return _ohlcv()

    monkeypatch.setattr(v2_router, "_fetch_history", _fetch)

    result = await v2_router.analyze_symbol("BTC", period="60d", interval="1h")
    assert calls == ["BTC-USD", "BTC"]
    assert result.symbol == "BTC"


@pytest.mark.asyncio
async def test_process_symbol_inside_scan_symbols_does_not_block_the_event_loop(monkeypatch):
    def _slow_fetch(symbol, period, interval):
        time.sleep(0.3)
        return _ohlcv()

    monkeypatch.setattr(v2_router, "_fetch_history", _slow_fetch)

    heartbeats = await _count_heartbeats_during(
        v2_router.scan_symbols(["AAPL"], interval="1h"), interval=0.02,
    )
    assert heartbeats >= 5


@pytest.mark.asyncio
async def test_run_v2_backtest_history_does_not_block_the_event_loop_during_the_fetch(monkeypatch):
    class _SlowTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, start, end, interval):
            time.sleep(0.3)
            return _ohlcv(rows=80)

    monkeypatch.setattr(v2_backtest.yf, "Ticker", _SlowTicker)

    heartbeats = await _count_heartbeats_during(
        v2_backtest.run_v2_backtest_history("AAPL", days=10), interval=0.02,
    )
    assert heartbeats >= 5


@pytest.mark.asyncio
async def test_analyze_symbol_raises_a_genuine_404_when_no_data_is_available(monkeypatch):
    """Production audit MEDIUM #9: the route's own `except Exception`
    used to re-catch the `HTTPException(404)` it had just raised for
    "no data available", turning it into a misleading 500. It must
    surface as a 404, not a 500."""
    monkeypatch.setattr(v2_router, "_fetch_history", lambda symbol, period, interval: pd.DataFrame())

    with pytest.raises(HTTPException) as exc_info:
        await v2_router.analyze_symbol("NO_SUCH_SYMBOL", period="60d", interval="1h")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_analyze_symbol_still_returns_500_for_a_genuine_unexpected_error(monkeypatch):
    def _broken_fetch(symbol, period, interval):
        raise RuntimeError("boom")

    monkeypatch.setattr(v2_router, "_fetch_history", _broken_fetch)

    with pytest.raises(HTTPException) as exc_info:
        await v2_router.analyze_symbol("AAPL", period="60d", interval="1h")

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_get_backtest_history_raises_a_genuine_404_when_no_data_is_available(monkeypatch):
    async def _empty_backtest(symbol, days):
        return []

    monkeypatch.setattr(v2_router, "run_v2_backtest_history", _empty_backtest)

    with pytest.raises(HTTPException) as exc_info:
        await v2_router.get_backtest_history("NO_SUCH_SYMBOL", days=30)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_backtest_history_still_returns_500_for_a_genuine_unexpected_error(monkeypatch):
    async def _broken_backtest(symbol, days):
        raise RuntimeError("boom")

    monkeypatch.setattr(v2_router, "run_v2_backtest_history", _broken_backtest)

    with pytest.raises(HTTPException) as exc_info:
        await v2_router.get_backtest_history("AAPL", days=30)

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_run_v2_backtest_history_returns_empty_list_when_no_data(monkeypatch):
    class _EmptyTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end, interval):
            return pd.DataFrame()

    monkeypatch.setattr(v2_backtest.yf, "Ticker", _EmptyTicker)

    result = await v2_backtest.run_v2_backtest_history("AAPL", days=10)
    assert result == []
