"""
Unit tests for core/investor_persona.py. The Groq client is fully mocked —
no network calls, no real LLM calls.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.ai_trader_persona import TradeSignal
from core.investor_persona import HorizonView, InvestorPersona, InvestorRecommendation
from core.regime_scanner import MarketRegime


def _mock_groq_response(payload: dict):
    tool_call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(payload)))
    message = SimpleNamespace(tool_calls=[tool_call])
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _valid_payload(**overrides):
    payload = {
        "symbol": "AAPL",
        "market_regime": "TRENDING_BULL",
        "horizon_1_week": {"signal": "BUY", "confidence_score": 60, "rationale": "Kısa vadeli momentum olumlu."},
        "horizon_1_month": {"signal": "BUY", "confidence_score": 65, "rationale": "Haftalık trend yukarı yönlü."},
        "horizon_1_year": {"signal": "STRONG_BUY", "confidence_score": 70, "rationale": "Rejim güçlü ve kalıcı görünüyor."},
        "investor_commentary": "Genel görünüm olumlu.",
    }
    payload.update(overrides)
    return payload


def _make_persona() -> InvestorPersona:
    persona = InvestorPersona(api_key="test-key")
    persona._client = MagicMock()
    return persona


class TestInvestorPersonaGenerateRecommendation:
    def test_returns_investor_recommendation(self):
        persona = _make_persona()
        persona._client.chat.completions.create.return_value = _mock_groq_response(_valid_payload())

        result = persona.generate_recommendation(
            symbol="AAPL",
            market_regime=MarketRegime.TRENDING_BULL,
            analysis={"current_price": 180.0, "macro": {}, "micro": {}},
        )

        assert isinstance(result, InvestorRecommendation)
        assert result.symbol == "AAPL"

    def test_all_three_horizons_present(self):
        persona = _make_persona()
        persona._client.chat.completions.create.return_value = _mock_groq_response(_valid_payload())

        result = persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

        assert isinstance(result.horizon_1_week, HorizonView)
        assert isinstance(result.horizon_1_month, HorizonView)
        assert isinstance(result.horizon_1_year, HorizonView)

    def test_horizons_can_have_different_signals(self):
        persona = _make_persona()
        payload = _valid_payload(
            horizon_1_week={"signal": "SELL", "confidence_score": 55, "rationale": "Kısa vadede aşırı alım."},
            horizon_1_year={"signal": "STRONG_BUY", "confidence_score": 80, "rationale": "Uzun vadeli rejim güçlü."},
        )
        persona._client.chat.completions.create.return_value = _mock_groq_response(payload)

        result = persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

        assert result.horizon_1_week.signal == TradeSignal.SELL
        assert result.horizon_1_year.signal == TradeSignal.STRONG_BUY

    def test_disclaimer_always_appended(self):
        persona = _make_persona()
        persona._client.chat.completions.create.return_value = _mock_groq_response(_valid_payload())

        result = persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

        assert "temel analiz" in result.investor_commentary.lower()

    def test_disclaimer_appended_after_custom_commentary(self):
        persona = _make_persona()
        payload = _valid_payload(investor_commentary="Özel bir yorum.")
        persona._client.chat.completions.create.return_value = _mock_groq_response(payload)

        result = persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

        assert result.investor_commentary.startswith("Özel bir yorum.")
        assert "temel analiz" in result.investor_commentary.lower()

    def test_raises_on_empty_tool_calls(self):
        persona = _make_persona()
        message = SimpleNamespace(tool_calls=[])
        persona._client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )

        with pytest.raises(RuntimeError, match="tool_calls boş"):
            persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

    def test_raises_on_invalid_schema(self):
        persona = _make_persona()
        bad_payload = _valid_payload()
        del bad_payload["horizon_1_year"]
        persona._client.chat.completions.create.return_value = _mock_groq_response(bad_payload)

        with pytest.raises(RuntimeError, match="beklenen şemaya uymuyor"):
            persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

    def test_confidence_score_out_of_range_rejected(self):
        persona = _make_persona()
        payload = _valid_payload(
            horizon_1_week={"signal": "BUY", "confidence_score": 150, "rationale": "geçersiz"}
        )
        persona._client.chat.completions.create.return_value = _mock_groq_response(payload)

        with pytest.raises(RuntimeError, match="beklenen şemaya uymuyor"):
            persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})
