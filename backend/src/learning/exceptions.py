"""OptiTrade Continuous Learning — exception types."""
from __future__ import annotations


class LearningError(Exception):
    """Base class for all Continuous Learning errors."""


class LearningPersistenceError(LearningError):
    """Raised when a learning sample, accuracy snapshot, weight update,
    or drift signal could not be read from or written to storage."""
