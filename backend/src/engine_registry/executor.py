"""
OptiTrade Engine Registry — engine execution.

Executes one registered engine (by name/version) or every currently
*enabled* engine, always producing `ExecutionMetadata` — including on
failure or when an engine is disabled — so a caller running "all engines"
can see exactly what happened to each one rather than only the
successes.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from engine_registry.exceptions import EngineNotFoundError
from engine_registry.models import ExecutionMetadata, ExecutionStatus
from engine_registry.registry import EngineRegistry

logger = logging.getLogger(__name__)


def execute_one(
    registry: EngineRegistry, engine_name: str, engine_version: str, symbol: str
) -> ExecutionMetadata:
    """Executes a single registered engine's `vote(symbol)`. Raises
    `EngineNotFoundError` if the (name, version) pair was never
    registered - unlike a failure *during* voting (which is captured in
    the returned metadata, not raised), an unknown engine is a caller
    error, not a runtime engine failure."""
    if not registry.is_enabled(engine_name, engine_version):
        return ExecutionMetadata(
            engine_name=engine_name, engine_version=engine_version,
            status=ExecutionStatus.DISABLED, duration_ms=0.0,
        )

    engine = registry.get(engine_name, engine_version)
    started_at = time.perf_counter()
    try:
        vote = engine.vote(symbol)
    except Exception as exc:
        duration_ms = (time.perf_counter() - started_at) * 1000
        log_event(
            logger, component="engine_registry", module="engine_registry.executor",
            operation="execute_one", status=STATUS_ERROR,
            engine_name=engine_name, engine_version=engine_version,
            error_type=type(exc).__name__, execution_time_ms=duration_ms,
            level=logging.WARNING,
        )
        return ExecutionMetadata(
            engine_name=engine_name, engine_version=engine_version,
            status=ExecutionStatus.FAILURE, duration_ms=duration_ms,
            error_type=type(exc).__name__,
        )

    duration_ms = (time.perf_counter() - started_at) * 1000
    log_event(
        logger, component="engine_registry", module="engine_registry.executor",
        operation="execute_one", status=STATUS_SUCCESS,
        engine_name=engine_name, engine_version=engine_version,
        execution_time_ms=duration_ms,
    )
    return ExecutionMetadata(
        engine_name=engine_name, engine_version=engine_version,
        status=ExecutionStatus.SUCCESS, duration_ms=duration_ms, vote=vote,
    )


def execute_all(registry: EngineRegistry, symbol: str) -> List[ExecutionMetadata]:
    """Executes every currently-enabled registered engine. Disabled
    engines are included in the returned list (status=DISABLED) rather
    than silently omitted, so callers can distinguish "didn't run because
    disabled" from "wasn't registered at all"."""
    results: List[ExecutionMetadata] = []
    for engine in registry.all():
        results.append(
            execute_one(registry, engine.engine_name, engine.engine_version, symbol)
        )
    return results
