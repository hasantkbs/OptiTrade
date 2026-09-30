"""
Regression tests proving `alert_scan_loop` (production audit: "An entire
advertised platform (Watchlist & Alerts) is unreachable... AlertScheduler
is never instantiated in main.py, never wired to a cron/background
task") and `paper_trading_fill_loop` (production audit: "Paper Trading's
resting orders silently never fill... scan_pending_orders() is never
invoked by anything") actually call their respective schedulers, and do
so through the executor thread pool rather than blocking the event loop
(same reasoning/technique as test_main_self_evolution_loop.py for
self_evolution_loop).
"""
import asyncio
import time

import pytest

import main as main_module


class _FakeReport:
    def __init__(self, triggered_count: int = 0) -> None:
        self.triggered_count = triggered_count


async def _run_one_cycle(loop_coro_factory, timeout: float = 1.5):
    task = asyncio.create_task(loop_coro_factory())
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_alert_scan_loop_calls_the_scheduler_without_blocking_the_event_loop(monkeypatch):
    calls = []

    class _FakeScheduler:
        def run_scan(self):
            calls.append("run_scan")
            time.sleep(0.3)
            return _FakeReport(triggered_count=2)

    monkeypatch.setattr(main_module, "_watchlist_scheduler", _FakeScheduler())
    monkeypatch.setattr(main_module, "_WATCHLIST_ALERT_SCAN_INTERVAL_SECONDS", 0.01)

    tick_times = []

    async def ticker() -> None:
        while True:
            await asyncio.sleep(0.01)
            tick_times.append(time.monotonic())

    ticker_task = asyncio.create_task(ticker())
    start = time.monotonic()
    await _run_one_cycle(main_module.alert_scan_loop)
    ticker_task.cancel()
    try:
        await ticker_task
    except (asyncio.CancelledError, Exception):
        pass

    assert calls, "run_scan() was never called"
    assert set(calls) == {"run_scan"}
    gaps = [b - a for a, b in zip([start] + tick_times[:-1], tick_times)]
    assert gaps and max(gaps) < 0.15, f"event loop was blocked for {max(gaps):.3f}s during run_scan()"


@pytest.mark.asyncio
async def test_alert_scan_loop_tolerates_no_scheduler_configured(monkeypatch):
    monkeypatch.setattr(main_module, "_watchlist_scheduler", None)
    monkeypatch.setattr(main_module, "_WATCHLIST_ALERT_SCAN_INTERVAL_SECONDS", 0.01)
    await _run_one_cycle(main_module.alert_scan_loop, timeout=0.2)  # must not raise


@pytest.mark.asyncio
async def test_paper_trading_fill_loop_calls_the_scheduler_without_blocking_the_event_loop(monkeypatch):
    calls = []

    class _FakeScheduler:
        def scan_pending_orders(self):
            calls.append("scan_pending_orders")
            time.sleep(0.3)
            return ["fill-1"]

    monkeypatch.setattr(main_module, "_paper_trading_scheduler", _FakeScheduler())
    monkeypatch.setattr(main_module, "_PAPER_TRADING_FILL_SCAN_INTERVAL_SECONDS", 0.01)

    tick_times = []

    async def ticker() -> None:
        while True:
            await asyncio.sleep(0.01)
            tick_times.append(time.monotonic())

    ticker_task = asyncio.create_task(ticker())
    start = time.monotonic()
    await _run_one_cycle(main_module.paper_trading_fill_loop)
    ticker_task.cancel()
    try:
        await ticker_task
    except (asyncio.CancelledError, Exception):
        pass

    assert calls, "scan_pending_orders() was never called"
    assert set(calls) == {"scan_pending_orders"}
    gaps = [b - a for a, b in zip([start] + tick_times[:-1], tick_times)]
    assert gaps and max(gaps) < 0.15, f"event loop was blocked for {max(gaps):.3f}s during scan_pending_orders()"


@pytest.mark.asyncio
async def test_paper_trading_fill_loop_tolerates_no_scheduler_configured(monkeypatch):
    monkeypatch.setattr(main_module, "_paper_trading_scheduler", None)
    monkeypatch.setattr(main_module, "_PAPER_TRADING_FILL_SCAN_INTERVAL_SECONDS", 0.01)
    await _run_one_cycle(main_module.paper_trading_fill_loop, timeout=0.2)  # must not raise
