"""Tests for dashboard/market_dashboard.py. A fake regime scanner keeps
the regime-distribution assertion deterministic; sector/news/feature
store calls are real (network/Redis/Postgres) - matching this
project's established testing philosophy of only faking genuinely
expensive/nondeterministic dependencies."""
import pytest

from core.regime_scanner import MarketRegime, ScannedSymbol
from dashboard.market_dashboard import MarketDashboardService


class _FakeRegimeScanner:
    def __init__(self, regime=MarketRegime.TRENDING_BULL):
        self._regime = regime

    def scan(self, symbols):
        return [
            ScannedSymbol(symbol=s, regime=self._regime, cumulative_return_pct=10.0, annualized_volatility_pct=15.0, trend_strength_r2=0.8, last_close=100.0)
            for s in symbols
        ]


@pytest.fixture
def service():
    return MarketDashboardService(regime_scanner=_FakeRegimeScanner())


def test_build_returns_regime_distribution(service):
    view = service.build(symbols=["AAPL", "MSFT", "GOOG"])
    assert view.regime_distribution == {"TRENDING_BULL": 3}


def test_build_returns_sector_heatmap(service):
    view = service.build(symbols=["AAPL"], market="US")
    assert isinstance(view.sector_heatmap, list)
    if view.sector_heatmap:
        assert view.sector_heatmap[0].sector is not None


def test_build_uses_default_symbols_when_none_given(service):
    view = service.build()
    assert sum(view.regime_distribution.values()) == len(service._config.default_market_symbols)


def test_build_survives_news_lookup_failures():
    class _AlwaysFailingRegimeScanner:
        def scan(self, symbols):
            return []

    service = MarketDashboardService(regime_scanner=_AlwaysFailingRegimeScanner())
    view = service.build(symbols=["THIS-IS-NOT-A-REAL-SYMBOL-XYZ"])
    assert isinstance(view.news_impact_summary, list)


# ─────────────────────────────────────────────────────────────────────────
# Feature Store failure resilience regression (production audit HIGH #6:
# "unguarded Feature Store call while the adjacent news call correctly
# handles the same failure class").
# ─────────────────────────────────────────────────────────────────────────

class _AlwaysFailingFeatureStore:
    def get_latest_feature(self, symbol, feature_name):
        raise RuntimeError("feature store unreachable")


class _PartiallyFailingFeatureStore:
    """Raises only for one specific symbol - proves failure isolation
    per-symbol, not just "the whole call happens not to raise"."""

    def __init__(self, failing_symbol: str, value: float = 5.0):
        self._failing_symbol = failing_symbol
        self._value = value

    def get_latest_feature(self, symbol, feature_name):
        if symbol == self._failing_symbol:
            raise RuntimeError("feature store unreachable for this symbol")

        class _Record:
            value = self._value

        return _Record()


def test_build_survives_a_feature_store_outage_across_every_symbol():
    service = MarketDashboardService(
        regime_scanner=_FakeRegimeScanner(), feature_store=_AlwaysFailingFeatureStore(),
    )
    view = service.build(symbols=["AAPL", "MSFT"])  # must not raise

    assert view.volatility_map == {}
    # the rest of the dashboard still comes through
    assert view.regime_distribution == {"TRENDING_BULL": 2}


def test_build_excludes_only_the_symbol_whose_feature_store_lookup_fails():
    service = MarketDashboardService(
        regime_scanner=_FakeRegimeScanner(), feature_store=_PartiallyFailingFeatureStore("MSFT", value=7.5),
    )
    view = service.build(symbols=["AAPL", "MSFT"])  # must not raise

    assert view.volatility_map == {"AAPL": 7.5}
    assert "MSFT" not in view.volatility_map


# ─────────────────────────────────────────────────────────────────────────
# news_impact_summary runs its per-symbol lookups concurrently (performance
# fix: this loop was serial, and a single cold get_news_summary() call can
# take 20-30s+ against live yfinance, making /dashboard/market's latency
# scale with symbol count on top of that per-symbol cost).
# ─────────────────────────────────────────────────────────────────────────

def test_build_isolates_a_single_news_lookup_failure_under_concurrent_execution(monkeypatch):
    def _fake_get_news_summary(symbol):
        if symbol == "MSFT":
            raise RuntimeError("yfinance unreachable for this symbol")
        return {"sentiment_score": 1.0, "sentiment_label": "positive", "headlines": [{"title": "x"}]}

    monkeypatch.setattr("dashboard.market_dashboard.get_news_summary", _fake_get_news_summary)

    service = MarketDashboardService(regime_scanner=_FakeRegimeScanner())
    view = service.build(symbols=["AAPL", "MSFT", "GOOGL"])

    returned_symbols = {snap.symbol for snap in view.news_impact_summary}
    assert returned_symbols == {"AAPL", "GOOGL"}
    assert "MSFT" not in returned_symbols


def test_build_runs_news_lookups_concurrently_not_serially(monkeypatch):
    import time as _time

    def _slow_fake_get_news_summary(symbol):
        _time.sleep(0.2)
        return {"sentiment_score": 0.0, "sentiment_label": "neutral", "headlines": []}

    monkeypatch.setattr("dashboard.market_dashboard.get_news_summary", _slow_fake_get_news_summary)

    service = MarketDashboardService(regime_scanner=_FakeRegimeScanner())
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]

    started = _time.monotonic()
    service.build(symbols=symbols)
    elapsed = _time.monotonic() - started

    assert elapsed < 0.2 * len(symbols), (
        f"took {elapsed:.2f}s for {len(symbols)} symbols at 0.2s each - looks serial"
    )
