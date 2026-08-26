"""
Regression test for the production audit's "self_evolution_loop blocks
the entire event loop once a day" Critical finding.

main.py's self_evolution_loop previously called validate_predictions()
and train_model() directly inside an `async def` - both are synchronous
and slow (network + CPU-bound), so every concurrent request to the
whole API would freeze for the duration of a daily validation/retrain
cycle. The fix routes both calls through the same `_run_in_executor`
helper (a real ThreadPoolExecutor) the rest of main.py already uses for
exactly this reason.

validate_predictions/train_model themselves hit yfinance and train a
real XGBoost model - genuinely expensive/nondeterministic external
work, so per this project's testing convention they're stubbed here;
the real PostgreSQL-backed FastAPI startup/wiring is exercised
elsewhere (test_main_backward_compatibility.py, test_main_*_endpoints.py).
"""
import asyncio
import time

import pytest

import main as main_module


@pytest.mark.asyncio
async def test_self_evolution_loop_does_not_block_the_event_loop(monkeypatch):
    calls = []
    BLOCK_SECONDS = 0.3

    def slow_validate_predictions():
        calls.append("validate")
        time.sleep(BLOCK_SECONDS)
        return 0

    def slow_train_model():
        calls.append("train")
        time.sleep(BLOCK_SECONDS)

    monkeypatch.setattr(main_module, "validate_predictions", slow_validate_predictions)
    monkeypatch.setattr(main_module, "train_model", slow_train_model)

    tick_times = []

    async def ticker() -> None:
        while True:
            await asyncio.sleep(0.01)
            tick_times.append(time.monotonic())

    loop_task = asyncio.create_task(main_module.self_evolution_loop())
    ticker_task = asyncio.create_task(ticker())
    start = time.monotonic()
    try:
        # self_evolution_loop's real per-cycle wait is asyncio.sleep(86400) -
        # it never returns on its own, so bound how long we wait for one
        # validate+train cycle to complete instead of letting it run forever.
        await asyncio.wait_for(asyncio.shield(loop_task), timeout=2.0)
    except asyncio.TimeoutError:
        pass
    finally:
        loop_task.cancel()
        ticker_task.cancel()
        for task in (loop_task, ticker_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    assert calls == ["validate", "train"]

    # The ticker wakes every 10ms. If self_evolution_loop still called
    # the (now synchronous, BLOCK_SECONDS-long) stubs directly on the
    # event loop instead of through _run_in_executor, the loop itself
    # would be frozen for the full BLOCK_SECONDS of each call and the
    # gap between two consecutive ticks would spike to roughly that
    # duration. Routed through the executor, no single gap should ever
    # approach BLOCK_SECONDS - this directly proves the event loop
    # stayed responsive the whole time validate/train were "running".
    gaps = [b - a for a, b in zip([start] + tick_times[:-1], tick_times)]
    assert gaps, "ticker never got a chance to run at all"
    max_gap = max(gaps)
    assert max_gap < BLOCK_SECONDS / 2, (
        f"event loop was blocked for {max_gap:.3f}s (>= half of the "
        f"{BLOCK_SECONDS}s synchronous call) - validate/train are not running in the executor"
    )
