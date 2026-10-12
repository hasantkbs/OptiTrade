"""
Unit tests for the provider abstraction layer.

These tests exercise:
  - providers/base.py  — Protocol contract
  - providers/registry.py  — singleton and override/reset API
  - providers/yfinance_provider.py  — structural conformance (no live network calls)

No yfinance network calls are made: YFinanceProvider is only checked for
Protocol conformance and structure, not live data.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from typing import Optional
import pandas as pd
import pytest

from providers.base import MarketDataProvider
from providers.registry import (
    get_market_provider, override_provider, reset_provider,
)
from providers.yfinance_provider import YFinanceProvider


# ── Stub provider for isolation tests ────────────────────────────────────────

class _StubProvider:
    """Minimal provider that satisfies the Protocol without network access."""

    def fetch_ohlcv(self, symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
        if symbol == "MISSING":
            return None
        return pd.DataFrame(
            {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [1000]},
        )

    def fetch_info(self, symbol: str) -> dict:
        return {"forwardEps": 2.0, "trailingEps": 1.5}

    def get_balance_status(self, symbol: str) -> str:
        return "Pozitif"


# ── Protocol conformance ──────────────────────────────────────────────────────

class TestMarketDataProviderProtocol:
    def test_stub_satisfies_protocol(self):
        stub = _StubProvider()
        assert isinstance(stub, MarketDataProvider)

    def test_yfinance_provider_satisfies_protocol(self):
        provider = YFinanceProvider()
        assert isinstance(provider, MarketDataProvider)

    def test_plain_object_does_not_satisfy_protocol(self):
        class _Incomplete:
            def fetch_ohlcv(self, symbol: str, period: str = "6mo"):
                return None
            # missing fetch_info and get_balance_status

        assert not isinstance(_Incomplete(), MarketDataProvider)


# ── Registry ──────────────────────────────────────────────────────────────────

class TestProviderRegistry:
    def setup_method(self):
        reset_provider()

    def teardown_method(self):
        reset_provider()

    def test_get_returns_provider(self):
        provider = get_market_provider()
        assert provider is not None

    def test_get_returns_same_instance(self):
        a = get_market_provider()
        b = get_market_provider()
        assert a is b

    def test_override_replaces_singleton(self):
        stub = _StubProvider()
        override_provider(stub)
        assert get_market_provider() is stub

    def test_reset_clears_singleton(self):
        override_provider(_StubProvider())
        reset_provider()
        # After reset, a new instance is created
        provider = get_market_provider()
        assert not isinstance(provider, _StubProvider)

    def test_default_provider_is_hybrid(self):
        from providers.hybrid_provider import HybridProvider
        provider = get_market_provider()
        assert isinstance(provider, HybridProvider)

    def test_yfinance_provider_selectable_via_env(self, monkeypatch):
        monkeypatch.setenv("MARKET_DATA_PROVIDER", "YFINANCE")
        reset_provider()
        provider = get_market_provider()
        assert isinstance(provider, YFinanceProvider)
        reset_provider()

    def test_override_is_used_by_fetcher(self):
        from providers.registry import override_provider, reset_provider
        from data.fetcher import fetch_history
        stub = _StubProvider()
        override_provider(stub)
        result = fetch_history("AAPL", period="6mo")
        assert result is not None
        reset_provider()

    def test_missing_symbol_returns_none_via_stub(self):
        from data.fetcher import fetch_history
        override_provider(_StubProvider())
        result = fetch_history("MISSING", period="6mo")
        assert result is None
        reset_provider()

    def test_balance_status_via_stub(self):
        from data.fetcher import get_balance_status
        override_provider(_StubProvider())
        status = get_balance_status("AAPL")
        assert status == "Pozitif"
        reset_provider()


# ── YFinanceProvider structure ────────────────────────────────────────────────

class TestYFinanceProviderStructure:
    """Verify YFinanceProvider has the required methods — no network calls."""

    def test_has_fetch_ohlcv(self):
        assert callable(getattr(YFinanceProvider, "fetch_ohlcv", None))

    def test_has_fetch_info(self):
        assert callable(getattr(YFinanceProvider, "fetch_info", None))

    def test_has_get_balance_status(self):
        assert callable(getattr(YFinanceProvider, "get_balance_status", None))

    def test_has_fetch_bist100_volume(self):
        assert callable(getattr(YFinanceProvider, "fetch_bist100_volume", None))

    def test_instantiation_no_args(self):
        provider = YFinanceProvider()
        assert provider is not None


# ── YFinanceProvider hard deadline (no live network calls - a fake Ticker
# simulates the hang) ──────────────────────────────────────────────────────

class TestYFinanceProviderTimeoutHandling:
    """A hung yfinance call (observed live: an invalid/delisted symbol via
    /price/{symbol} took 30s+ despite yfinance's own internal per-request
    timeout default, because its retry/backoff compounds across several
    requests) must not block the caller past _FETCH_TIMEOUT_SECONDS - see
    providers/yfinance_provider.py's own module comment."""

    def test_fetch_ohlcv_returns_none_instead_of_blocking_past_the_deadline(self, monkeypatch):
        import time
        import providers.yfinance_provider as yfp

        monkeypatch.setattr(yfp, "_FETCH_TIMEOUT_SECONDS", 0.1)

        class _HangingTicker:
            def history(self, period):
                time.sleep(1.0)
                return pd.DataFrame()

        monkeypatch.setattr(yfp.yf, "Ticker", lambda symbol: _HangingTicker())

        provider = YFinanceProvider()
        start = time.monotonic()
        result = provider.fetch_ohlcv("SLOW", period="1mo")
        elapsed = time.monotonic() - start

        assert result is None
        assert elapsed < 0.5, f"fetch_ohlcv blocked for {elapsed:.2f}s past its own 0.1s deadline"

    def test_fetch_info_returns_empty_dict_instead_of_blocking_past_the_deadline(self, monkeypatch):
        import time
        import providers.yfinance_provider as yfp

        monkeypatch.setattr(yfp, "_FETCH_TIMEOUT_SECONDS", 0.1)

        class _HangingTicker:
            @property
            def info(self):
                time.sleep(1.0)
                return {}

        monkeypatch.setattr(yfp.yf, "Ticker", lambda symbol: _HangingTicker())

        provider = YFinanceProvider()
        start = time.monotonic()
        result = provider.fetch_info("SLOW")
        elapsed = time.monotonic() - start

        assert result == {}
        assert elapsed < 0.5, f"fetch_info blocked for {elapsed:.2f}s past its own 0.1s deadline"

    def test_fetch_ohlcv_still_returns_real_data_on_a_fast_call(self, monkeypatch):
        import providers.yfinance_provider as yfp

        class _FastTicker:
            def history(self, period):
                return pd.DataFrame({"Close": [1.0, 2.0]})

        monkeypatch.setattr(yfp.yf, "Ticker", lambda symbol: _FastTicker())

        provider = YFinanceProvider()
        result = provider.fetch_ohlcv("AAPL", period="1mo")
        assert result is not None and not result.empty

    def test_fetch_info_still_returns_real_data_on_a_fast_call(self, monkeypatch):
        import providers.yfinance_provider as yfp

        class _FastTicker:
            info = {"forwardEps": 2.0}

        monkeypatch.setattr(yfp.yf, "Ticker", lambda symbol: _FastTicker())

        provider = YFinanceProvider()
        result = provider.fetch_info("AAPL")
        assert result == {"forwardEps": 2.0}
