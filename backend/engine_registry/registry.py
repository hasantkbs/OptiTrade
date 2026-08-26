"""
OptiTrade Engine Registry — the registry itself.

Distinct from (and more capable than) `decision_engine.registry.
VotingEngineRegistry`: this registry validates interface compatibility on
registration, keys engines by (engine_name, engine_version) so multiple
versions of the same engine can coexist, rejects duplicate
(name, version) registrations, and supports enabling/disabling an engine
without unregistering it.

`default_registry` is the process-wide instance real, self-registering
engines target by convention (see `discovery.py`); tests should construct
their own isolated `EngineRegistry()` instead of using the shared global,
to avoid cross-test pollution.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.interfaces import VotingEngineProtocol
from engine_registry.exceptions import (
    DuplicateEngineError,
    EngineNotFoundError,
    IncompatibleEngineError,
)

logger = logging.getLogger(__name__)

_EngineKey = Tuple[str, str]  # (engine_name, engine_version)


class EngineRegistry:
    """Holds registered voting engines, keyed by (engine_name, engine_version)."""

    def __init__(self) -> None:
        self._engines: Dict[_EngineKey, VotingEngineProtocol] = {}
        self._enabled: Dict[_EngineKey, bool] = {}

    def register(self, engine: VotingEngineProtocol) -> None:
        """Registers `engine`, validating it satisfies
        `VotingEngineProtocol` and rejecting an exact (name, version)
        duplicate. Newly registered engines are enabled by default."""
        if not isinstance(engine, VotingEngineProtocol):
            log_event(
                logger, component="engine_registry", module="engine_registry.registry",
                operation="register", status=STATUS_ERROR,
                error_type="IncompatibleEngineError",
            )
            raise IncompatibleEngineError(repr(engine))

        key = (engine.engine_name, engine.engine_version)
        if key in self._engines:
            log_event(
                logger, component="engine_registry", module="engine_registry.registry",
                operation="register", status=STATUS_ERROR,
                engine_name=engine.engine_name, engine_version=engine.engine_version,
                error_type="DuplicateEngineError",
            )
            raise DuplicateEngineError(*key)

        self._engines[key] = engine
        self._enabled[key] = True
        log_event(
            logger, component="engine_registry", module="engine_registry.registry",
            operation="register", status=STATUS_SUCCESS,
            engine_name=engine.engine_name, engine_version=engine.engine_version,
        )

    def unregister(self, engine_name: str, engine_version: str) -> None:
        key = (engine_name, engine_version)
        if key not in self._engines:
            raise EngineNotFoundError(engine_name, engine_version)
        del self._engines[key]
        del self._enabled[key]
        log_event(
            logger, component="engine_registry", module="engine_registry.registry",
            operation="unregister", status=STATUS_SUCCESS,
            engine_name=engine_name, engine_version=engine_version,
        )

    def get(self, engine_name: str, engine_version: str) -> VotingEngineProtocol:
        key = (engine_name, engine_version)
        if key not in self._engines:
            raise EngineNotFoundError(engine_name, engine_version)
        return self._engines[key]

    def versions_of(self, engine_name: str) -> List[str]:
        """All registered version strings for a given engine name."""
        return [version for (name, version) in self._engines if name == engine_name]

    def enable(self, engine_name: str, engine_version: str) -> None:
        key = (engine_name, engine_version)
        if key not in self._engines:
            raise EngineNotFoundError(engine_name, engine_version)
        self._enabled[key] = True
        log_event(
            logger, component="engine_registry", module="engine_registry.registry",
            operation="enable", status=STATUS_SUCCESS,
            engine_name=engine_name, engine_version=engine_version,
        )

    def disable(self, engine_name: str, engine_version: str) -> None:
        key = (engine_name, engine_version)
        if key not in self._engines:
            raise EngineNotFoundError(engine_name, engine_version)
        self._enabled[key] = False
        log_event(
            logger, component="engine_registry", module="engine_registry.registry",
            operation="disable", status=STATUS_SUCCESS,
            engine_name=engine_name, engine_version=engine_version,
        )

    def is_enabled(self, engine_name: str, engine_version: str) -> bool:
        key = (engine_name, engine_version)
        if key not in self._engines:
            raise EngineNotFoundError(engine_name, engine_version)
        return self._enabled[key]

    def all(self) -> List[VotingEngineProtocol]:
        """Every registered engine, enabled or not."""
        return list(self._engines.values())

    def all_enabled(self) -> List[VotingEngineProtocol]:
        """Only currently-enabled registered engines."""
        return [engine for key, engine in self._engines.items() if self._enabled[key]]

    def clear(self) -> None:
        """Removes every registered engine. Primarily for test isolation
        when using the shared `default_registry`."""
        self._engines.clear()
        self._enabled.clear()

    def __len__(self) -> int:
        return len(self._engines)


default_registry = EngineRegistry()
