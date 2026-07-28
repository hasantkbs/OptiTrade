"""
OptiTrade Explanation Engine — domain models.

The Explanation Engine never predicts and never votes - it only turns
an already-final `decision_engine.models.DecisionOutput` into a
plain-language explanation. `provider` records which path actually
produced the text (`groq` vs the deterministic `fallback`), so a
degraded response is always distinguishable from a normal one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ExplanationProvider(str, Enum):
    GROQ = "groq"
    FALLBACK = "fallback"


class Explanation(BaseModel):
    text: str
    provider: ExplanationProvider
    model: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
