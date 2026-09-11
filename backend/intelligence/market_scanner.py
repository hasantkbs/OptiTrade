"""
OptiTrade Intelligence Primitives — Market Scanner.

Batch orchestration over the canonical `pipeline.PipelineService.run()`
- the ONLY production analysis path (Technical + Fundamental + News ->
Decision Engine -> DecisionOutput -> Explanation, already fully
implemented). This module never re-implements or bypasses that path:
it submits each requested symbol to it under bounded concurrency and a
per-symbol timeout, isolating one symbol's failure from the rest of
the batch.

`PipelineService.run()` already persists every decision via its own
`decision_engine.repository.PostgresExecutionRepository` - this
scanner adds no new table and stores nothing of its own. It is a pure
orchestration layer over an already-complete, already-persisting
production path.

`scan()` is a plain synchronous method (matching `PipelineService.run`'s
own synchronous nature and `watchlist.scheduler.AlertScheduler.run_scan`'s
identical convention), so a future background loop can invoke it via
`await _run_in_executor(scanner.scan, symbols)`, exactly like
`main.py`'s existing `alert_scan_loop` already does for `AlertScheduler`.
No scheduler, periodic loop, or new concurrency framework is introduced
here - only the reusable primitive itself.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from typing import List, Optional, Protocol, runtime_checkable

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from intelligence.config import MarketScannerConfig
from intelligence.models import MarketScanResult, ScanSymbolFailure, ScanSymbolResult, ScanSymbolStatus
from pipeline.models import PipelineResponse

logger = logging.getLogger(__name__)

_MODULE = "intelligence.market_scanner"
_COMPONENT = "intelligence"


@runtime_checkable
class PipelineRunnerProtocol(Protocol):
    """The only contract this scanner depends on -
    `pipeline.service.PipelineService`'s real shape. Defined here
    (rather than importing the concrete class as a type) so tests can
    inject a fake without constructing a real `PipelineService` (which
    requires a live Feature Store / Model Serving / Postgres
    connection)."""

    def run(self, symbol: str) -> PipelineResponse: ...


def _call_with_timeout(func, timeout_seconds: float):
    """Identical shape to `pipeline.executor._call_with_timeout` and
    `watchlist.scheduler._call_with_timeout`: runs `func` in its own
    single-worker pool and enforces `timeout_seconds` on the caller's
    wait, without blocking on an abandoned call - `shutdown(wait=False)`
    lets this return as soon as the timeout elapses; Python cannot
    forcibly stop a running thread, so the orphaned call simply
    finishes in the background."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False)


class MarketScanner:
    """Runs `PipelineService.run(symbol)` for many symbols under
    bounded concurrency. Never raises for a per-symbol failure - every
    outcome (success, timeout, or failure) is captured in the returned
    `MarketScanResult`."""

    def __init__(
        self,
        pipeline_service: Optional[PipelineRunnerProtocol] = None,
        config: Optional[MarketScannerConfig] = None,
    ) -> None:
        self.config = config or MarketScannerConfig.from_env()
        if pipeline_service is None:
            from pipeline.service import PipelineService

            pipeline_service = PipelineService()
        self.pipeline_service = pipeline_service
        self._pool = ThreadPoolExecutor(max_workers=self.config.max_parallel_symbols)

    def scan(self, symbols: List[str]) -> MarketScanResult:
        """Scans `symbols` through the canonical pipeline. Blank
        entries are dropped; remaining symbols are uppercased (matching
        `PipelineService.run`'s own normalization) and deduplicated,
        preserving first-occurrence order. `successful`/`failed` in the
        result are reported in that same deterministic order, never
        completion order."""
        scan_started_at = time.perf_counter()
        started_dt = datetime.now(timezone.utc)
        requested_count = len(symbols)

        normalized = [symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()]
        unique_symbols = list(dict.fromkeys(normalized))
        unique_count = len(unique_symbols)

        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="scan_start", status=STATUS_SUCCESS,
            requested_count=requested_count, unique_count=unique_count,
        )

        if not unique_symbols:
            completed_dt = datetime.now(timezone.utc)
            return MarketScanResult(
                requested_count=requested_count, unique_symbols=[], unique_count=0,
                successful=[], failed=[], successful_count=0, failed_count=0,
                started_at=started_dt, completed_at=completed_dt,
                duration_ms=(time.perf_counter() - scan_started_at) * 1000,
            )

        futures = {symbol: self._pool.submit(self._scan_one, symbol) for symbol in unique_symbols}
        outcomes = {symbol: future.result() for symbol, future in futures.items()}

        successful = [outcome for symbol in unique_symbols if isinstance(outcome := outcomes[symbol], ScanSymbolResult)]
        failed = [outcome for symbol in unique_symbols if isinstance(outcome := outcomes[symbol], ScanSymbolFailure)]

        completed_dt = datetime.now(timezone.utc)
        duration_ms = (time.perf_counter() - scan_started_at) * 1000
        result = MarketScanResult(
            requested_count=requested_count, unique_symbols=unique_symbols, unique_count=unique_count,
            successful=successful, failed=failed,
            successful_count=len(successful), failed_count=len(failed),
            started_at=started_dt, completed_at=completed_dt, duration_ms=duration_ms,
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="scan_complete", status=STATUS_SUCCESS,
            requested_count=requested_count, unique_count=unique_count,
            successful_count=result.successful_count, failed_count=result.failed_count,
            execution_time_ms=duration_ms,
        )
        return result

    def _scan_one(self, symbol: str):
        started_at = time.perf_counter()
        try:
            response = _call_with_timeout(lambda: self.pipeline_service.run(symbol), self.config.symbol_timeout_seconds)
        except FutureTimeoutError:
            duration_ms = (time.perf_counter() - started_at) * 1000
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="scan_symbol", status=STATUS_ERROR,
                symbol=symbol, error_type="TimeoutError", execution_time_ms=duration_ms, level=logging.WARNING,
            )
            return ScanSymbolFailure(
                symbol=symbol, status=ScanSymbolStatus.TIMEOUT, error_type="TimeoutError", duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - started_at) * 1000
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="scan_symbol", status=STATUS_ERROR,
                symbol=symbol, error_type=type(exc).__name__, execution_time_ms=duration_ms, level=logging.WARNING,
            )
            return ScanSymbolFailure(
                symbol=symbol, status=ScanSymbolStatus.FAILED, error_type=type(exc).__name__, duration_ms=duration_ms,
            )

        duration_ms = (time.perf_counter() - started_at) * 1000
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="scan_symbol", status=STATUS_SUCCESS,
            symbol=symbol, execution_time_ms=duration_ms,
        )
        return ScanSymbolResult(symbol=symbol, status=ScanSymbolStatus.SUCCESS, response=response, duration_ms=duration_ms)

    def shutdown(self) -> None:
        """Matches `watchlist.scheduler.AlertScheduler.shutdown()`'s
        exact convention - `wait=False` so this never blocks on
        whatever is still in flight."""
        self._pool.shutdown(wait=False)
