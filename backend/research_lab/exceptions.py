"""OptiTrade Research Lab — exception types."""
from __future__ import annotations


class ResearchLabError(Exception):
    """Base class for all Research Lab errors."""


class ResearchLabPersistenceError(ResearchLabError):
    """Raised when a Research Lab artifact could not be read from or
    written to storage."""


class InvalidExperimentTransitionError(ResearchLabError):
    """Raised when an experiment status transition is not allowed by
    the lifecycle graph (see `experiments/lifecycle.py`)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"cannot transition experiment from {current!r} to {target!r}")


class MissingHypothesisError(ResearchLabError):
    """Raised when an experiment is created without a written
    hypothesis - every experiment must begin with one."""
