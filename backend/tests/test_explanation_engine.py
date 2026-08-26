"""Tests for backend/explanation_engine/."""
from datetime import datetime, timezone

import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from explanation_engine.config import ExplanationEngineConfig
from explanation_engine.exceptions import ExplanationProviderError
from explanation_engine.fallback import generate_fallback_explanation
from explanation_engine.groq_provider import GroqExplanationProvider
from explanation_engine.interfaces import ExplanationProviderProtocol
from explanation_engine.models import Explanation, ExplanationProvider
from explanation_engine.service import ExplanationEngine


def _decision(prediction=Prediction.BUY, evidence=None, engine_results=None) -> DecisionOutput:
    vote = EngineVote(
        engine_name="TechnicalEngine", engine_version="v1", prediction=prediction, confidence=0.75,
        expected_return=2.5, volatility=13.0, evidence=["bullish crossover"],
    )
    return DecisionOutput(
        symbol="AAPL", decision=prediction, confidence=0.7, expected_return=2.5, expected_volatility=13.0,
        aggregation_strategy_version="v1", data_sufficiency=1.0,
        evidence=evidence if evidence is not None else ["TechnicalEngine: bullish crossover"],
        engine_results=engine_results if engine_results is not None else [vote],
    )


# ─────────────────────────────────────────────────────────────────────────
# models.py / config.py
# ─────────────────────────────────────────────────────────────────────────

def test_explanation_defaults_have_a_timestamp():
    explanation = Explanation(text="x", provider=ExplanationProvider.FALLBACK)
    assert explanation.generated_at is not None


def test_config_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("EXPLANATION_ENGINE_TEMPERATURE", "0.9")
    monkeypatch.setenv("EXPLANATION_ENGINE_MAX_TOKENS", "128")
    config = ExplanationEngineConfig.from_env()
    assert config.temperature == 0.9
    assert config.max_tokens == 128


def test_config_defaults():
    config = ExplanationEngineConfig()
    assert config.max_evidence_items == 8
    assert config.timeout_seconds == 10.0


# ─────────────────────────────────────────────────────────────────────────
# fallback.py (pure, deterministic)
# ─────────────────────────────────────────────────────────────────────────

def test_fallback_explanation_mentions_symbol_and_decision():
    decision = _decision(Prediction.BUY)
    text = generate_fallback_explanation(decision, "AAPL")
    assert "AAPL" in text
    assert "BUY" in text


def test_fallback_explanation_handles_no_engine_results():
    decision = _decision(engine_results=[])
    text = generate_fallback_explanation(decision, "AAPL")
    assert "no engine produced a valid vote" in text


def test_fallback_explanation_is_deterministic():
    decision = _decision(Prediction.SELL)
    assert generate_fallback_explanation(decision, "AAPL") == generate_fallback_explanation(decision, "AAPL")


# ─────────────────────────────────────────────────────────────────────────
# service.py — provider abstraction, fallback on failure
# ─────────────────────────────────────────────────────────────────────────

class _FakeProvider:
    provider_name = "fake"

    def __init__(self, text: str = "a fake explanation", raises: bool = False):
        self._text = text
        self._raises = raises

    def generate(self, decision: DecisionOutput, symbol: str) -> str:
        if self._raises:
            raise ExplanationProviderError("simulated failure")
        return self._text


def test_service_uses_injected_provider_on_success():
    engine = ExplanationEngine(provider=_FakeProvider(text="custom explanation"))
    result = engine.explain(_decision(), "AAPL")
    assert result.provider == ExplanationProvider.GROQ
    assert result.text == "custom explanation"


def test_service_falls_back_when_provider_raises():
    engine = ExplanationEngine(provider=_FakeProvider(raises=True))
    result = engine.explain(_decision(), "AAPL")
    assert result.provider == ExplanationProvider.FALLBACK
    assert "AAPL" in result.text


def test_service_provider_property_is_lazy_and_cached():
    engine = ExplanationEngine()
    assert engine._provider is None
    first = engine.provider
    second = engine.provider
    assert first is second
    assert isinstance(first, GroqExplanationProvider)


def test_fake_provider_satisfies_protocol():
    assert isinstance(_FakeProvider(), ExplanationProviderProtocol)


# ─────────────────────────────────────────────────────────────────────────
# groq_provider.py — real Groq API call (network)
# ─────────────────────────────────────────────────────────────────────────

def test_real_groq_provider_generates_a_nonempty_explanation():
    provider = GroqExplanationProvider()
    text = provider.generate(_decision(Prediction.BUY), "AAPL")
    assert isinstance(text, str)
    assert len(text.strip()) > 0


def test_groq_provider_raises_on_empty_content(monkeypatch):
    provider = GroqExplanationProvider()

    class _FakeMessage:
        content = "   "

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    monkeypatch.setattr(provider._client.chat.completions, "create", lambda **kwargs: _FakeResponse())
    with pytest.raises(ExplanationProviderError):
        provider.generate(_decision(), "AAPL")


def test_real_groq_provider_raises_explanation_provider_error_on_bad_key():
    provider = GroqExplanationProvider(api_key="invalid-key-xyz")
    with pytest.raises(ExplanationProviderError):
        provider.generate(_decision(), "AAPL")


def test_real_end_to_end_service_uses_groq_for_a_real_decision():
    engine = ExplanationEngine()
    result = engine.explain(_decision(Prediction.HOLD), "AAPL")
    assert result.provider == ExplanationProvider.GROQ
    assert len(result.text) > 0
