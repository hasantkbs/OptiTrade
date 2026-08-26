"""Tests for portfolio/recommendations.py (Recommendation Engine,
requirement 7). Real PostgreSQL; deterministic fake price/history
fetchers; a fake pipeline_service stands in for `pipeline.service.
PipelineService` to test Decision Engine-signal recommendations without
constructing the whole production Pipeline."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from decision_engine.models import Prediction
from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.models import RecommendationType
from portfolio.prices import PriceService
from portfolio.recommendations import RecommendationEngine
from portfolio.repository import PortfolioRepository
from portfolio.risk import RiskAnalyticsService
from portfolio.service import PortfolioService

_OWNER_PREFIX = "reco-test-owner"
_CURRENT_PRICES = {"AAPL": 200.0, "MSFT": 350.0}


def _fake_current_price_fetcher(symbol, period="5d"):
    price = _CURRENT_PRICES.get(symbol)
    if price is None:
        return pd.DataFrame()
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=5, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [price] * 5}, index=dates)


def _fake_history_fetcher(symbol, start, end):
    base_price = _CURRENT_PRICES.get(symbol, 100.0)
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    seed = sum(ord(character) for character in symbol) % (2 ** 31)
    rng = np.random.RandomState(seed)
    daily_returns = rng.normal(0.0004, 0.015, size=len(dates))
    prices = base_price * np.cumprod(1 + daily_returns)
    return pd.DataFrame({"Close": prices}, index=dates)


class _FakeDecisionResponse:
    def __init__(self, decision: Prediction, confidence: float) -> None:
        self.decision = decision
        self.confidence = confidence


class _FakePipelineService:
    def __init__(self, decisions):
        self._decisions = decisions

    def run(self, symbol):
        return self._decisions[symbol]


@pytest.fixture
def repository():
    repo = PortfolioRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM portfolio_transactions WHERE portfolio_id IN "
                "(SELECT id FROM portfolio_portfolios WHERE owner LIKE %s)", (f"{_OWNER_PREFIX}%",),
            )
            cur.execute("DELETE FROM portfolio_portfolios WHERE owner LIKE %s", (f"{_OWNER_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def price_service():
    config = PortfolioConfig(redis_host="localhost", redis_port=6379, redis_db=15, price_cache_ttl_seconds=60, lookback_days=120)
    service = PriceService(
        config=config, current_price_fetcher=_fake_current_price_fetcher, history_fetcher=_fake_history_fetcher,
    )
    service._client.flushdb()
    yield service
    service._client.flushdb()


@pytest.fixture
def portfolio_service(repository, price_service):
    return PortfolioService(repository=repository, price_service=price_service)


@pytest.fixture
def analytics_service(portfolio_service):
    return PositionAnalyticsService(portfolio_service=portfolio_service)


@pytest.fixture
def risk_service(analytics_service, price_service):
    return RiskAnalyticsService(position_analytics_service=analytics_service, config=price_service.config)


def test_generate_returns_nothing_for_an_empty_portfolio(portfolio_service, analytics_service, risk_service):
    engine = RecommendationEngine(position_analytics_service=analytics_service, risk_analytics_service=risk_service)
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-empty", name="Empty")
    assert engine.generate(portfolio.id) == []


def test_overweight_position_triggers_an_overweight_recommendation(portfolio_service, analytics_service, risk_service):
    engine = RecommendationEngine(position_analytics_service=analytics_service, risk_analytics_service=risk_service)
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-overweight", name="Overweight")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 40, 150.0)  # 6000/10000 = 60%, well above the 25% threshold

    recommendations = engine.generate(portfolio.id)
    types = {recommendation.recommendation_type for recommendation in recommendations}
    assert RecommendationType.OVERWEIGHT in types
    assert RecommendationType.CONCENTRATION in types


def test_rebalance_recommendation_only_appears_when_target_weights_given(portfolio_service, analytics_service, risk_service):
    engine = RecommendationEngine(position_analytics_service=analytics_service, risk_analytics_service=risk_service)
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-rebalance", name="Rebalance")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)

    assert not any(
        r.recommendation_type == RecommendationType.REBALANCE for r in engine.generate(portfolio.id)
    )
    with_target = engine.generate(portfolio.id, target_weights_pct={"AAPL": 90.0})
    assert any(r.recommendation_type == RecommendationType.REBALANCE for r in with_target)


def test_decision_signal_recommendation_for_held_sell_signal(portfolio_service, analytics_service, risk_service):
    pipeline_service = _FakePipelineService({"AAPL": _FakeDecisionResponse(Prediction.SELL, 0.8)})
    engine = RecommendationEngine(
        position_analytics_service=analytics_service, risk_analytics_service=risk_service,
        pipeline_service=pipeline_service,
    )
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-sell-signal", name="SellSignal")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)  # material weight (>5%)

    recommendations = engine.generate(portfolio.id)
    decision_recs = [r for r in recommendations if r.recommendation_type == RecommendationType.DECISION_SIGNAL]
    assert len(decision_recs) == 1
    assert decision_recs[0].related_decision == Prediction.SELL
    assert decision_recs[0].symbol == "AAPL"


def test_no_decision_signal_recommendations_without_a_pipeline_service(portfolio_service, analytics_service, risk_service):
    engine = RecommendationEngine(position_analytics_service=analytics_service, risk_analytics_service=risk_service)
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-no-pipeline", name="NoPipeline")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)
    recommendations = engine.generate(portfolio.id)
    assert not any(r.recommendation_type == RecommendationType.DECISION_SIGNAL for r in recommendations)


def test_service_defaults_to_real_dependencies():
    engine = RecommendationEngine()
    assert isinstance(engine.position_analytics_service, PositionAnalyticsService)
    assert engine.pipeline_service is None
