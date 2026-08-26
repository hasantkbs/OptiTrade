"""
OptiTrade Explanation Engine.

Turns an already-final `decision_engine.models.DecisionOutput` into a
plain-language explanation. Never predicts, never votes - LLMs here
only explain a decision that deterministic voting engines already
made. Provider-abstracted (`interfaces.ExplanationProviderProtocol`);
Groq is the first concrete provider. Any provider failure degrades to
a deterministic, non-LLM fallback rather than failing the caller.
"""
from explanation_engine.models import Explanation, ExplanationProvider
from explanation_engine.service import ExplanationEngine

__all__ = ["ExplanationEngine", "Explanation", "ExplanationProvider"]
