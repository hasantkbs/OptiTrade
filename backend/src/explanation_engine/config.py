"""OptiTrade Explanation Engine — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Groq retired every llama-3.x chat model from its catalog (calling one
# now 404s with "model_not_found") - confirmed live against
# client.models.list() on 2026-09-29. openai/gpt-oss-120b is the
# largest current general-purpose chat model on Groq and is more than
# enough for a 2-4 sentence plain-text explanation of an already-final
# decision (see this module's docstring: never used for prediction).
_DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


@dataclass(frozen=True)
class ExplanationEngineConfig:
    model: str = _DEFAULT_MODEL
    temperature: float = 0.3
    max_tokens: int = 512
    timeout_seconds: float = 10.0
    max_evidence_items: int = 8

    @classmethod
    def from_env(cls) -> "ExplanationEngineConfig":
        load_dotenv()
        return cls(
            model=os.getenv("EXPLANATION_ENGINE_MODEL", os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")),
            temperature=float(os.getenv("EXPLANATION_ENGINE_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("EXPLANATION_ENGINE_MAX_TOKENS", "512")),
            timeout_seconds=float(os.getenv("EXPLANATION_ENGINE_TIMEOUT_SECONDS", "10.0")),
            max_evidence_items=int(os.getenv("EXPLANATION_ENGINE_MAX_EVIDENCE_ITEMS", "8")),
        )
