"""OptiTrade Intelligence Primitives — exception types."""
from __future__ import annotations


class IntelligenceError(Exception):
    """Base class for all intelligence-primitive errors."""


class NoDecisionHistoryError(IntelligenceError):
    """Raised when a symbol has no persisted `DecisionOutput` at all yet
    (nothing in `decision_engine_executions`), so there is no "current"
    decision to report a change for."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"no decision history available for {symbol!r}")
