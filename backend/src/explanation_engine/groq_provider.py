"""
OptiTrade Explanation Engine — Groq provider.

Mirrors the Groq client construction already established in
`core/ai_trader_persona.py` (`Groq(api_key=...)`, `GROQ_API_KEY`/
`GROQ_MODEL` env vars) - but deliberately does NOT use tool-calling to
extract a structured prediction the way `AITraderPersona` does. This
provider only ever asks for a plain-text explanation of an
already-final decision; its output is never parsed back into a
prediction, confidence, or price target, and is never fed into any
decision-making code path. That separation is what makes "the LLM
never predicts" an architectural guarantee rather than a policy.
"""
from __future__ import annotations

from typing import Optional

from groq import Groq

from decision_engine.models import DecisionOutput
from explanation_engine.config import ExplanationEngineConfig
from explanation_engine.exceptions import ExplanationProviderError

_SYSTEM_PROMPT = (
    "You are an explanation-only assistant for a quantitative trading system. "
    "A separate, deterministic Decision Engine has ALREADY made a final BUY, HOLD, "
    "or SELL decision using statistical voting engines - no language model was "
    "involved in reaching it. Your only job is to explain, in clear plain language "
    "for a retail trader, why that decision was reached, using only the evidence "
    "provided to you. You must NEVER propose a different decision, NEVER invent a "
    "new price target or prediction, NEVER contradict the given decision, and NEVER "
    "present your explanation as independent trading advice. Keep it concise: 2-4 "
    "sentences."
)


class GroqExplanationProvider:
    """Calls Groq's chat completions API for a plain-text explanation.
    Never uses function/tool calling - there is no structured output to
    extract, only prose."""

    provider_name = "groq"

    def __init__(self, api_key: Optional[str] = None, config: Optional[ExplanationEngineConfig] = None) -> None:
        self.config = config or ExplanationEngineConfig.from_env()
        self._client = Groq(api_key=api_key) if api_key else Groq()

    def generate(self, decision: DecisionOutput, symbol: str) -> str:
        prompt = self._build_prompt(decision, symbol)
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                timeout=self.config.timeout_seconds,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as exc:
            raise ExplanationProviderError(f"groq explanation request failed: {exc}") from exc

        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            raise ExplanationProviderError("groq returned an empty explanation")
        return content.strip()

    def _build_prompt(self, decision: DecisionOutput, symbol: str) -> str:
        import json

        payload = {
            "symbol": symbol,
            "decision": decision.decision.value,
            "confidence": round(decision.confidence, 4),
            "expected_return_pct": round(decision.expected_return, 4),
            "expected_volatility_pct": round(decision.expected_volatility, 4),
            "data_sufficiency": round(decision.data_sufficiency, 4),
            "contributing_engines": [
                {
                    "engine_name": vote.engine_name, "prediction": vote.prediction.value,
                    "confidence": round(vote.confidence, 4),
                }
                for vote in decision.engine_results
            ],
            "evidence": decision.evidence[: self.config.max_evidence_items],
        }
        return (
            "Explain why the trading system reached this already-final decision, "
            "using the evidence below. Do not suggest a different action.\n\n"
            f"{json.dumps(payload, default=str, indent=2)}"
        )
