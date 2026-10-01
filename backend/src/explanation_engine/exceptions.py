"""OptiTrade Explanation Engine — exception types."""
from __future__ import annotations


class ExplanationEngineError(Exception):
    """Base class for all Explanation Engine errors."""


class ExplanationProviderError(ExplanationEngineError):
    """Raised when a provider fails to produce an explanation (request
    error, timeout, empty response). `service.py` always catches this
    and falls back to a deterministic explanation - it is never allowed
    to fail a pipeline run."""
