"""OptiTrade Explanation Engine — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


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
            model=os.getenv("EXPLANATION_ENGINE_MODEL", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")),
            temperature=float(os.getenv("EXPLANATION_ENGINE_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("EXPLANATION_ENGINE_MAX_TOKENS", "512")),
            timeout_seconds=float(os.getenv("EXPLANATION_ENGINE_TIMEOUT_SECONDS", "10.0")),
            max_evidence_items=int(os.getenv("EXPLANATION_ENGINE_MAX_EVIDENCE_ITEMS", "8")),
        )
