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
