"""OptiTrade Decision Engine — exception types."""
from __future__ import annotations


class DecisionEngineError(Exception):
    """Base class for all Decision Engine errors."""


class NoValidVotesError(DecisionEngineError):
    """Raised when every registered voting engine either failed to
    execute or produced an invalid vote, so no decision can be made."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"No valid votes available for {symbol!r}")


class ExecutionPersistenceError(DecisionEngineError):
    """Raised when a completed decision could not be stored for future
    learning. The decision itself is still valid and returned to the
    caller — only persistence failed."""
