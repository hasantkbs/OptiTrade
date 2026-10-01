"""
OptiTrade Explanation Engine — provider interface.

Any future provider (a different LLM vendor, a local model, ...) only
needs to satisfy this `Protocol` - `service.py` never depends on a
concrete provider class.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from decision_engine.models import DecisionOutput


@runtime_checkable
class ExplanationProviderProtocol(Protocol):
    """Contract every explanation provider must satisfy. `generate()`
    may raise on failure - `service.py` catches it and falls back to a
    deterministic, non-LLM explanation rather than failing the
    request."""

    provider_name: str

    def generate(self, decision: DecisionOutput, symbol: str) -> str: ...
