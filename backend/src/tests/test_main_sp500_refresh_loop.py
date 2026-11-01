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
async def test_sp500_refresh_loop_fetches_immediately_on_startup_not_after_a_full_day(tmp_path, monkeypatch):
    """Final-review fix: the original sleep-first loop meant a fresh
    deploy or restart served the 28-symbol fallback for a full 24h
    before ever attempting a real fetch - on a host that redeploys
    several times a day, the real list could effectively never
    appear. _SP500_REFRESH_INTERVAL_SECONDS is set absurdly high here
    specifically so it would never fire within this test's window -
    only the immediate, pre-loop attempt can be what writes the file."""
    import core.market_config as market_config

    path = tmp_path / "sp500_symbols.json"
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))
    monkeypatch.setattr(main_module, "_SP500_REFRESH_INTERVAL_SECONDS", 999)
    monkeypatch.setattr(main_module, "_fetch_sp500_symbols_from_wikipedia", lambda: {"AAPL": "Apple"})

    await _run_one_cycle(main_module.sp500_refresh_loop, timeout=0.05)

    assert json.loads(path.read_text()) == {"sp500_symbols": {"AAPL": "Apple"}}


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
    monkeypatch.setattr(main_module.pd, "read_html", lambda url, **kwargs: [fake_table])
    monkeypatch.setattr(main_module, "_MIN_PLAUSIBLE_SP500_SYMBOLS", 0)

    result = main_module._fetch_sp500_symbols_from_wikipedia()

    assert result["AAPL"] == "Apple"  # legal-suffix stripping also applies here
    assert result["BRK-B"] == "Berkshire Hathaway"
    assert "BRK.B" not in result


def test_fetch_sp500_symbols_from_wikipedia_sends_a_user_agent(monkeypatch):
    """Final-review fix: Wikipedia rejects pandas' default request
    (pandas/urllib's own User-Agent) with HTTP 403 - confirmed live
    against en.wikipedia.org during review. Without a real User-Agent
    header, sp500_refresh_loop logs an error on every run and the
    cache file is never written, so get_us_symbols() silently serves
    the 28-symbol fallback forever."""
    import pandas as pd

    captured_kwargs = {}

    def _fake_read_html(url, **kwargs):
        captured_kwargs.update(kwargs)
        return [pd.DataFrame({"Symbol": ["AAPL"], "Security": ["Apple Inc."]})]

    monkeypatch.setattr(main_module.pd, "read_html", _fake_read_html)
    monkeypatch.setattr(main_module, "_MIN_PLAUSIBLE_SP500_SYMBOLS", 0)

    main_module._fetch_sp500_symbols_from_wikipedia()

    user_agent = captured_kwargs.get("storage_options", {}).get("User-Agent", "")
    assert user_agent, "no User-Agent header was sent - Wikipedia returns 403 without one"


def test_fetch_sp500_symbols_from_wikipedia_strips_legal_suffixes_from_company_names(monkeypatch):
    """Final-review fix: Wikipedia's real company names carry legal
    suffixes the original curated 28-symbol dict never had ("Apple"
    vs. "Apple Inc."). Left unstripped, news/entity_extraction.py's
    company-name matching (which requires the literal phrase in
    article text) stops recognizing headlines that say just "Apple"
    or "Meta" once the real list populates - a real regression for
    marquee tickers' news relevance, not just a cosmetic naming
    difference."""
    import pandas as pd

    fake_table = pd.DataFrame({
        "Symbol": ["AAPL", "V", "GOOGL", "MMM"],
        "Security": ["Apple Inc.", "Visa Inc.", "Alphabet Inc. (Class A)", "3M"],
    })
    monkeypatch.setattr(main_module.pd, "read_html", lambda url, **kwargs: [fake_table])
    monkeypatch.setattr(main_module, "_MIN_PLAUSIBLE_SP500_SYMBOLS", 0)

    result = main_module._fetch_sp500_symbols_from_wikipedia()

    assert result["AAPL"] == "Apple"
    assert result["V"] == "Visa"
    assert result["GOOGL"] == "Alphabet"
    assert result["MMM"] == "3M"  # no suffix to strip - unchanged


def test_fetch_sp500_symbols_from_wikipedia_rejects_a_suspiciously_small_table():
    """A structurally-valid but wrong table (e.g. Wikipedia's page
    layout changes and tables[0] becomes a different, much smaller
    table) must never be treated as a real S&P 500 fetch - the real
    index has ~500 constituents, not a handful."""
    import pandas as pd
    import pytest as _pytest

    fake_table = pd.DataFrame({"Symbol": ["AAPL", "MSFT"], "Security": ["Apple Inc.", "Microsoft"]})

    import unittest.mock as mock
    with mock.patch.object(main_module.pd, "read_html", lambda url, **kwargs: [fake_table]):
        with _pytest.raises(ValueError):
            main_module._fetch_sp500_symbols_from_wikipedia()


@pytest.mark.asyncio
async def test_sp500_refresh_loop_leaves_the_cache_untouched_when_the_fetch_result_is_too_small(tmp_path, monkeypatch):
    """sp500_refresh_loop must treat _fetch_sp500_symbols_from_wikipedia
    raising (the suspiciously-small-table case above) exactly like any
    other fetch failure: logged, existing cache left untouched - never
    silently overwritten with a handful of symbols."""
    import core.market_config as market_config

    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"AAPL": "Apple"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))
    monkeypatch.setattr(main_module, "_SP500_REFRESH_INTERVAL_SECONDS", 0.01)

    def _raise_too_small():
        raise ValueError("Wikipedia tablosu beklenenden çok az sembol döndürdü (2)")

    monkeypatch.setattr(main_module, "_fetch_sp500_symbols_from_wikipedia", _raise_too_small)

    await _run_one_cycle(main_module.sp500_refresh_loop)  # must not raise

    assert json.loads(path.read_text()) == {"sp500_symbols": {"AAPL": "Apple"}}
