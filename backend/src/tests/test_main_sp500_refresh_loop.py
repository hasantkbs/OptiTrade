"""sp500_refresh_loop keeps core.market_config.SP500_SYMBOLS_PATH's
cache current from Wikipedia's S&P 500 constituent table, once a day -
mirrors research/retrain_chart_models.py's own "infra failure never
destroys good data" principle, and market_opportunities_refresh_loop's
own test style/_run_one_cycle helper (test_main_background_scan_loops.py)."""
import asyncio
import json

import pytest

import main as main_module


async def _run_one_cycle(loop_coro_factory, timeout: float = 0.2):
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
async def test_sp500_refresh_loop_writes_the_cache_file_on_a_successful_fetch(tmp_path, monkeypatch):
    import core.market_config as market_config

    path = tmp_path / "sp500_symbols.json"
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))
    monkeypatch.setattr(main_module, "_SP500_REFRESH_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(main_module, "_fetch_sp500_symbols_from_wikipedia", lambda: {"AAPL": "Apple"})

    await _run_one_cycle(main_module.sp500_refresh_loop)

    assert json.loads(path.read_text()) == {"sp500_symbols": {"AAPL": "Apple"}}


@pytest.mark.asyncio
async def test_sp500_refresh_loop_leaves_the_existing_cache_untouched_on_fetch_failure(tmp_path, monkeypatch):
    import core.market_config as market_config

    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"AAPL": "Apple"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))
    monkeypatch.setattr(main_module, "_SP500_REFRESH_INTERVAL_SECONDS", 0.01)

    def _raise():
        raise RuntimeError("wikipedia unreachable")

    monkeypatch.setattr(main_module, "_fetch_sp500_symbols_from_wikipedia", _raise)

    await _run_one_cycle(main_module.sp500_refresh_loop)  # must not raise

    assert json.loads(path.read_text()) == {"sp500_symbols": {"AAPL": "Apple"}}


def test_fetch_sp500_symbols_from_wikipedia_normalizes_dot_tickers_to_hyphens(monkeypatch):
    """Wikipedia's table uses dot notation for dual-class shares
    (BRK.B); yfinance expects the hyphen convention (BRK-B) - an
    unnormalized ticker would be silently unfetchable everywhere
    downstream."""
    import pandas as pd

    fake_table = pd.DataFrame({
        "Symbol": ["AAPL", "BRK.B"],
        "Security": ["Apple Inc.", "Berkshire Hathaway"],
    })
    monkeypatch.setattr(main_module.pd, "read_html", lambda url: [fake_table])

    result = main_module._fetch_sp500_symbols_from_wikipedia()

    assert result["AAPL"] == "Apple Inc."
    assert result["BRK-B"] == "Berkshire Hathaway"
    assert "BRK.B" not in result
