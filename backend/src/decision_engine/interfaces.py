"""
OptiTrade Decision Engine — structural interfaces (Protocols).

Mirrors the pattern established in `core/interfaces.py` (Sprint 1) and
`feature_store/interfaces.py`: each `Protocol` names only the methods the
Decision Engine actually calls, so concrete voting engines (Technical,
Fundamental, News — built in later steps) and the execution repository
can be typed and tested against these without depending on any one
concrete implementation.
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from decision_engine.models import DecisionOutput, EngineVote


@runtime_checkable
class VotingEngineProtocol(Protocol):
    """Contract every voting engine (Technical, Fundamental, News, ...)
    must satisfy. `vote()` may raise on failure — the Decision Engine
    catches and logs per-engine failures rather than letting one engine's
    error abort the whole decision."""

    engine_name: str
    engine_version: str

    def vote(self, symbol: str) -> EngineVote: ...


@runtime_checkable
class ExecutionRepositoryProtocol(Protocol):
    """Contract for persisting completed decisions for future learning."""

    def save(self, output: DecisionOutput) -> None: ...

    def get_recent(self, symbol: str, limit: int = 10) -> List[DecisionOutput]: ...
