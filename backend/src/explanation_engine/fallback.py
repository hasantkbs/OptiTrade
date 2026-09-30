"""
OptiTrade Explanation Engine — deterministic fallback.

Used whenever the configured provider (Groq) fails, times out, or is
unreachable - the pipeline must never fail a request just because an
LLM call didn't succeed. Purely templated from the `DecisionOutput`
itself; no LLM involved.
"""
from __future__ import annotations

from decision_engine.models import DecisionOutput


def generate_fallback_explanation(decision: DecisionOutput, symbol: str) -> str:
    if decision.engine_results:
        engines_text = "; ".join(
            f"{vote.engine_name} voted {vote.prediction.value} ({vote.confidence:.0%} confidence)"
            for vote in decision.engine_results
        )
    else:
        engines_text = "no engine produced a valid vote"

    return (
        f"{symbol}: the Decision Engine reached {decision.decision.value} with "
        f"{decision.confidence:.0%} confidence, an expected return of "
        f"{decision.expected_return:+.2f}% and expected volatility of "
        f"{decision.expected_volatility:.2f}%. Contributing engines: {engines_text}. "
        f"Data sufficiency: {decision.data_sufficiency:.0%}."
    )
