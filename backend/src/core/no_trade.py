"""
OptiTrade — NO_TRADE Outcome Types
=====================================
Implements CTO Remediation Plan (docs/architecture/CTO_REMEDIATION_PLAN.md)
Revision 4, Section 5: the explicit outcome `core.hybrid_engine` produces
when the canonical Decision Engine cannot supply a direction for a symbol
(exception, zero valid votes, or insufficient data). A `NoTradeOutcome` is
never mapped to `HOLD` or any LLM-authored signal, and is never serialized
to a public API response — callers (`core.hybrid_engine._process_symbol`)
log it as an operational event and drop the symbol from the returned list
(Section 5.5's legacy array-contract).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class NoTradeReason(str, Enum):
    """Mirrors docs/architecture/CTO_REMEDIATION_PLAN.md Section 5.1."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # valid votes, but data_sufficiency below threshold
    DECISION_ENGINE_UNAVAILABLE = "DECISION_ENGINE_UNAVAILABLE"  # decide() raised (not NoValidVotesError)
    NO_VALID_ENGINE_VOTES = "NO_VALID_ENGINE_VOTES"  # decide(strict=True) raised NoValidVotesError


class NoTradeOutcome(BaseModel):
    """Carries no trade parameters of any kind, by construction - no
    `signal`, `confidence_score`, `entry_price`, `stop_loss`, or
    `take_profit_*` field exists on this model at all, so there is
    nothing for a caller to accidentally read as a real decision."""

    symbol: str
    reason: NoTradeReason
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Deliberately NOT "llm" - an LLM is never a valid signal_source value.
# "no_trade" is defined for completeness (Section 5.1's type) even though
# a NoTradeOutcome itself is never attached to a response object that
# carries `signal_source` - it is dropped before any such object exists.
SignalSource = Literal["decision_engine", "no_trade"]
