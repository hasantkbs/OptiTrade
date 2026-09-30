"""
OptiTrade Decision Engine — voting engine registry.

A minimal, in-process registry of the voting engines the Decision Engine
should consult. Concrete engines (Technical, Fundamental, News — built in
later steps) register themselves here; the Decision Engine never
constructs a concrete engine itself, only iterates whatever is registered.
"""
from __future__ import annotations

from typing import List

from decision_engine.interfaces import VotingEngineProtocol


class VotingEngineRegistry:
    """Holds the set of voting engines the Decision Engine executes."""

    def __init__(self) -> None:
        self._engines: List[VotingEngineProtocol] = []

    def register(self, engine: VotingEngineProtocol) -> None:
        self._engines.append(engine)

    def all(self) -> List[VotingEngineProtocol]:
        """Returns a snapshot copy — mutating the returned list does not
        affect the registry."""
        return list(self._engines)

    def __len__(self) -> int:
        return len(self._engines)
