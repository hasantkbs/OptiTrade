"""
Unit tests for core/ai_trader_persona.py. The Groq client is fully mocked -
no network calls, no real LLM calls.

CTO Remediation Plan (docs/architecture/CTO_REMEDIATION_PLAN.md) Revision
4, Task 0.1 / Finding F8: the LLM must never generate, override, or
preserve a final BUY/SELL decision or trade-execution parameters. These
tests verify that structurally, at both the schema level (what is actually
sent to Groq) and the parsing level (what survives even a non-compliant
provider response).
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.ai_trader_persona import _RECOMMENDATION_SCHEMA, AITraderPersona, TradeRecommendation
from core.regime_scanner import MarketRegime
from core.risk_manager import RiskLevels


def _mock_groq_response(payload: dict):
    tool_call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(payload)))
    message = SimpleNamespace(tool_calls=[tool_call])
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _valid_payload(**overrides):
    payload = {
        "symbol": "AAPL",
        "market_regime": "TRENDING_BULL",
        "trader_analysis": "Kısa vadeli momentum olumlu.",
        "investor_analysis": "Rejim yukarı yönlü.",
        "trader_commentary": "Genel görünüm olumlu.",
    }
    payload.update(overrides)
    return payload


def _make_persona() -> AITraderPersona:
    persona = AITraderPersona(api_key="test-key")
    persona._client = MagicMock()
    return persona


def _risk() -> RiskLevels:
    return RiskLevels(
        entry_price=180.0, atr=2.5, stop_loss=176.25, take_profit_1=185.0,
        take_profit_2=187.5, risk_per_unit=3.75, reward_per_unit_tp1=5.0,
        risk_reward_ratio=1.33, is_valid=True,
    )


class TestRecommendationSchema:
    """Finding F8's primary fix: the LLM's tool-calling schema has no
    way to request a final decision or trade-level parameters."""

    def test_schema_does_not_ask_for_signal_or_confidence(self):
        assert "signal" not in _RECOMMENDATION_SCHEMA["properties"]
        assert "confidence_score" not in _RECOMMENDATION_SCHEMA["properties"]

    def test_schema_does_not_ask_for_trade_levels(self):
        for field in ("entry_price", "stop_loss", "take_profit_1", "take_profit_2"):
            assert field not in _RECOMMENDATION_SCHEMA["properties"]

    def test_schema_only_asks_for_narrative_fields(self):
        assert _RECOMMENDATION_SCHEMA["properties"].keys() == {
            "symbol", "market_regime", "trader_analysis", "investor_analysis", "trader_commentary",
        }
        assert set(_RECOMMENDATION_SCHEMA["required"]) == _RECOMMENDATION_SCHEMA["properties"].keys()

    def test_schema_rejects_additional_properties(self):
        assert _RECOMMENDATION_SCHEMA["additionalProperties"] is False


class TestAITraderPersonaGenerateRecommendation:
    def test_returns_trade_recommendation_with_narrative_fields(self):
        persona = _make_persona()
        persona._client.chat.completions.create.return_value = _mock_groq_response(_valid_payload())

        result = persona.generate_recommendation(
            symbol="AAPL", market_regime=MarketRegime.TRENDING_BULL,
            analysis={"current_price": 180.0}, risk=_risk(),
        )

        assert isinstance(result, TradeRecommendation)
        assert result.symbol == "AAPL"
        assert result.trader_commentary == "Genel görünüm olumlu."

    def test_decision_fields_are_none_on_a_compliant_response(self):
        """The ordinary case: Groq honors the schema and never sends
        these fields at all - they default to None."""
        persona = _make_persona()
        persona._client.chat.completions.create.return_value = _mock_groq_response(_valid_payload())

        result = persona.generate_recommendation(
            symbol="AAPL", market_regime=MarketRegime.TRENDING_BULL,
            analysis={"current_price": 180.0}, risk=_risk(),
        )

        assert result.signal is None
        assert result.confidence_score is None
        assert result.entry_price is None
        assert result.stop_loss is None
        assert result.take_profit_1 is None
        assert result.take_profit_2 is None
        assert result.signal_source is None

    def test_decision_fields_are_scrubbed_even_on_a_non_compliant_response(self):
        """Structural backstop (task item 3): even if a provider ignores
        `additionalProperties: False` and includes these fields anyway,
        AITraderPersona must not let them survive - core.hybrid_engine
        is the only thing that may ever set them, from the canonical
        Decision Engine, never from the LLM."""
        persona = _make_persona()
        malicious_payload = _valid_payload(
            signal="STRONG_BUY", confidence_score=99,
            entry_price=999.0, stop_loss=1.0, take_profit_1=2.0, take_profit_2=3.0,
            signal_source="decision_engine",
        )
        persona._client.chat.completions.create.return_value = _mock_groq_response(malicious_payload)

        result = persona.generate_recommendation(
            symbol="AAPL", market_regime=MarketRegime.TRENDING_BULL,
            analysis={"current_price": 180.0}, risk=_risk(),
        )

        assert result.signal is None
        assert result.confidence_score is None
        assert result.entry_price is None
        assert result.stop_loss is None
        assert result.take_profit_1 is None
        assert result.take_profit_2 is None
        assert result.signal_source is None
        # The narrative fields from the same (otherwise valid) payload
        # are untouched - only the forbidden fields are scrubbed.
        assert result.trader_commentary == "Genel görünüm olumlu."

    def test_raises_on_empty_tool_calls(self):
        persona = _make_persona()
        message = SimpleNamespace(tool_calls=[])
        persona._client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )

        with pytest.raises(RuntimeError, match="tool_calls boş"):
            persona.generate_recommendation(
                symbol="AAPL", market_regime=MarketRegime.TRENDING_BULL,
                analysis={"current_price": 180.0}, risk=_risk(),
            )

    def test_raises_on_invalid_schema(self):
        persona = _make_persona()
        bad_payload = _valid_payload()
        del bad_payload["trader_commentary"]
        persona._client.chat.completions.create.return_value = _mock_groq_response(bad_payload)

        with pytest.raises(RuntimeError, match="beklenen şemaya uymuyor"):
            persona.generate_recommendation(
                symbol="AAPL", market_regime=MarketRegime.TRENDING_BULL,
                analysis={"current_price": 180.0}, risk=_risk(),
            )
