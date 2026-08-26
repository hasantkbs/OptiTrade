"""
OptiTrade Pipeline — parallel engine execution.

Runs every voting engine concurrently (one submission per engine to a
shared thread pool), enforcing a per-attempt timeout and a configurable
retry count for each engine independently, so one slow or failing
engine never blocks or fails the others. A timed-out call cannot be
forcibly killed (a fundamental limitation of Python threads) - this
simply stops waiting for it and records a timeout; the abandoned call
runs to completion in the background and its only side effect (e.g. a
Feature Store write) is otherwise harmless.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.interfaces import VotingEngineProtocol
from decision_engine.validation import validate_vote
from pipeline.config import PipelineConfig
from pipeline.models import EngineExecutionResult, EngineExecutionStatus

logger = logging.getLogger(__name__)


def _call_with_timeout(func, timeout_seconds: float):
    """Runs `func` in its own single-worker pool and enforces
    `timeout_seconds` on the caller's wait. Deliberately does NOT use
    the pool as a context manager: `ThreadPoolExecutor.__exit__` calls
    `shutdown(wait=True)`, which would block until the orphaned thread
    actually finishes - silently defeating the timeout from the
    caller's perspective. `shutdown(wait=False)` lets this return as
    soon as the timeout elapses; the abandoned thread keeps running in
    the background (Python cannot forcibly stop it) and is cleaned up
    once it eventually completes."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False)


class ParallelEngineExecutor:
    """Collects votes from every engine concurrently. Never raises -
    every engine's outcome (success, timeout, failure, or invalid
    vote) is captured as an `EngineExecutionResult`, giving the caller
    graceful degradation for free."""

    def __init__(self, config: Optional[PipelineConfig] = None, pool: Optional[ThreadPoolExecutor] = None) -> None:
        self.config = config or PipelineConfig.from_env()
        self._pool = pool or ThreadPoolExecutor(max_workers=self.config.max_parallel_workers)

    def collect_votes(self, engines: List[VotingEngineProtocol], symbol: str) -> List[EngineExecutionResult]:
        futures = [self._pool.submit(self._collect_one, engine, symbol) for engine in engines]
        return [future.result() for future in futures]

    def _collect_one(self, engine: VotingEngineProtocol, symbol: str) -> EngineExecutionResult:
        engine_name = getattr(engine, "engine_name", type(engine).__name__)
        engine_version = getattr(engine, "engine_version", "unknown")
        total_attempts = self.config.max_retries + 1

        last_status = EngineExecutionStatus.FAILED
        last_error_type: Optional[str] = None
        started_at = time.perf_counter()

        for attempt in range(1, total_attempts + 1):
            try:
                vote = _call_with_timeout(lambda: engine.vote(symbol), self.config.engine_timeout_seconds)
            except FutureTimeoutError:
                last_status = EngineExecutionStatus.TIMEOUT
                last_error_type = "TimeoutError"
                self._log_attempt(engine_name, symbol, attempt, STATUS_ERROR, last_error_type)
                continue
            except Exception as exc:
                last_status = EngineExecutionStatus.FAILED
                last_error_type = type(exc).__name__
                self._log_attempt(engine_name, symbol, attempt, STATUS_ERROR, last_error_type)
                continue

            validation = validate_vote(vote)
            if not validation.is_valid:
                last_status = EngineExecutionStatus.INVALID
                last_error_type = "InvalidVoteError"
                self._log_attempt(engine_name, symbol, attempt, STATUS_ERROR, last_error_type)
                continue

            duration_ms = (time.perf_counter() - started_at) * 1000
            self._log_attempt(engine_name, symbol, attempt, STATUS_SUCCESS, None)
            return EngineExecutionResult(
                engine_name=engine_name, engine_version=engine_version, status=EngineExecutionStatus.SUCCESS,
                vote=vote, error_type=None, duration_ms=duration_ms, attempts=attempt,
            )

        duration_ms = (time.perf_counter() - started_at) * 1000
        return EngineExecutionResult(
            engine_name=engine_name, engine_version=engine_version, status=last_status,
            vote=None, error_type=last_error_type, duration_ms=duration_ms, attempts=total_attempts,
        )

    @staticmethod
    def _log_attempt(engine_name: str, symbol: str, attempt: int, status: str, error_type: Optional[str]) -> None:
        log_event(
            logger, component="pipeline", module="pipeline.executor", operation="collect_vote",
            status=status, symbol=symbol, engine_name=engine_name, attempt=attempt,
            error_type=error_type, level=logging.WARNING if status == STATUS_ERROR else logging.INFO,
        )
