"""
Unit tests for api/v1/endpoints/signals.py. HybridTradingEngine is replaced
via FastAPI dependency override with a MagicMock — no network calls, no
LLM calls. The shared slowapi rate limiter is reset before/after each test
to avoid cross-test bleed (it's process-global state).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.v1.endpoints import signals
from core.ai_trader_persona import TradeRecommendation, TradeSignal
from core.investor_persona import HorizonView, InvestorRecommendation
from core.market_anomaly_detector import MarketAlert
from core.rate_limiter import limiter


def _trade_rec():
    return TradeRecommendation(
        symbol="AAPL", market_regime="TRENDING_BULL",
        trader_analysis="a", investor_analysis="b",
        signal=TradeSignal.BUY, confidence_score=70,
        entry_price=180.0, stop_loss=175.0, take_profit_1=185.0, take_profit_2=190.0,
        trader_commentary="c",
    )


def _investor_rec():
    horizon = HorizonView(signal=TradeSignal.BUY, confidence_score=60, rationale="r")
    return InvestorRecommendation(
        symbol="AAPL", market_regime="TRENDING_BULL",
        horizon_1_week=horizon, horizon_1_month=horizon, horizon_1_year=horizon,
        investor_commentary="genel",
    )


@pytest.fixture
def client():
    limiter.reset()
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(signals.router)

    mock_engine = MagicMock()
    app.dependency_overrides[signals.get_engine] = lambda: mock_engine

    with TestClient(app) as test_client:
        test_client.mock_engine = mock_engine
        yield test_client

    app.dependency_overrides.clear()
    limiter.reset()


class TestAnalyzeEndpoint:
    def test_default_profile_is_trader(self, client):
        client.mock_engine.run.return_value = [_trade_rec()]

        response = client.post("/signals/analyze", json={"symbols": ["AAPL"]})

        assert response.status_code == 200
        client.mock_engine.run.assert_called_once_with(["AAPL"], profile="trader")

    def test_investor_profile_passed_through(self, client):
        client.mock_engine.run.return_value = [_investor_rec()]

        response = client.post("/signals/analyze", json={"symbols": ["AAPL"], "profile": "investor"})

        assert response.status_code == 200
        client.mock_engine.run.assert_called_once_with(["AAPL"], profile="investor")
        body = response.json()[0]
        assert "horizon_1_week" in body

    def test_trader_response_shape_preserved(self, client):
        client.mock_engine.run.return_value = [_trade_rec()]

        response = client.post("/signals/analyze", json={"symbols": ["AAPL"]})

        body = response.json()[0]
        assert body["entry_price"] == 180.0
        assert "horizon_1_week" not in body

    def test_invalid_profile_rejected(self, client):
        response = client.post("/signals/analyze", json={"symbols": ["AAPL"], "profile": "bogus"})
        assert response.status_code == 422

    def test_empty_result_returns_404(self, client):
        client.mock_engine.run.return_value = []
        response = client.post("/signals/analyze", json={"symbols": ["AAPL"]})
        assert response.status_code == 404


class TestAlertsEndpoint:
    def test_empty_alerts_returns_200(self, client):
        client.mock_engine.check_alerts.return_value = []

        response = client.post("/signals/alerts", json={"symbols": ["AAPL"]})

        assert response.status_code == 200
        assert response.json() == []

    def test_alerts_returned(self, client):
        alert = MarketAlert(
            symbol="AAPL", alert_type="PRICE_VOLUME_SHOCK", severity="MEDIUM",
            direction="BULLISH", message="test",
        )
        client.mock_engine.check_alerts.return_value = [alert]

        response = client.post("/signals/alerts", json={"symbols": ["AAPL"]})

        assert response.status_code == 200
        assert response.json()[0]["symbol"] == "AAPL"

    def test_symbols_passed_through(self, client):
        client.mock_engine.check_alerts.return_value = []

        client.post("/signals/alerts", json={"symbols": ["AAPL", "BTC-USD"]})

        client.mock_engine.check_alerts.assert_called_once_with(["AAPL", "BTC-USD"])
