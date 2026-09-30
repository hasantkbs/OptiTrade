"""OptiTrade Pipeline — exception types."""
from __future__ import annotations


class PipelineError(Exception):
    """Base class for all pipeline errors."""


class PipelineExecutionError(PipelineError):
    """Raised only for a genuinely unexpected internal failure (e.g.
    aggregation itself raising) - never for an individual engine
    failing, timing out, or returning an invalid vote, all of which are
    handled as graceful degradation and never raise."""
