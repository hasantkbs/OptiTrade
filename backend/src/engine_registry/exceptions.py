"""OptiTrade Engine Registry — exception types."""
from __future__ import annotations


class EngineRegistryError(Exception):
    """Base class for all Engine Registry errors."""


class IncompatibleEngineError(EngineRegistryError):
    """Raised when an object registered does not satisfy
    `decision_engine.interfaces.VotingEngineProtocol`."""

    def __init__(self, engine_repr: str) -> None:
        self.engine_repr = engine_repr
        super().__init__(
            f"{engine_repr} does not satisfy VotingEngineProtocol "
            f"(missing engine_name/engine_version/vote())"
        )


class DuplicateEngineError(EngineRegistryError):
    """Raised when the same (engine_name, engine_version) pair is
    registered more than once."""

    def __init__(self, engine_name: str, engine_version: str) -> None:
        self.engine_name = engine_name
        self.engine_version = engine_version
        super().__init__(
            f"Engine {engine_name!r} version {engine_version!r} is already registered"
        )


class EngineNotFoundError(EngineRegistryError):
    """Raised when looking up, enabling, disabling, or executing an
    engine (name, version) pair that was never registered."""

    def __init__(self, engine_name: str, engine_version: str) -> None:
        self.engine_name = engine_name
        self.engine_version = engine_version
        super().__init__(f"Engine {engine_name!r} version {engine_version!r} is not registered")
