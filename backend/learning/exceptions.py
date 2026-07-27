"""OptiTrade Continuous Learning — exception types."""
from __future__ import annotations


class LearningError(Exception):
    """Base class for all Continuous Learning errors."""


class LearningPersistenceError(LearningError):
    """Raised when a learning sample, accuracy snapshot, weight update,
    or drift signal could not be read from or written to storage."""


class OutcomeEvaluationError(LearningError):
    """Raised when a pending sample's actual market outcome could not be
    determined (e.g. no price data available for the symbol/date
    range). The sample is left unevaluated and retried on a later
    learning cycle rather than being marked evaluated with a fabricated
    outcome."""
