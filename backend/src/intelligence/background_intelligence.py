"""
OptiTrade Intelligence Primitives — Background Intelligence Orchestration.

Batches Phase C's `MarketScanner` and Phase D's `rank_opportunities()`
into one bounded, schedulable unit of work over the existing market
symbol universe (`core.market_config`) - never a second scanner, never
a second ranking algorithm, never a second scheduler framework. This
module produces GLOBAL market intelligence only: no portfolio/watchlist
mutation, no alert creation, no trade execution.

    BackgroundIntelligenceOrchestrator.run_once()
        universe_provider.get_symbols()      (core.market_config, read-only)
            -> bounded batch (rotating cursor, in-memory)
        MarketScanner.scan(batch)             (Phase C, unmodified)
            -> MarketScanResult
        rank_opportunities(scan_result)       (Phase D, unmodified)
            -> OpportunityRankingResult
        -> BackgroundScanResult

Cursor semantics are the same in-memory rotating offset
`watchlist.scheduler.AlertScheduler` already uses for its own periodic
global sweep (`self._scan_offset`): advances by the batch size each
tick, resets to 0 once it reaches (or would exceed) the universe
length. This is a deliberate choice, not an oversight - the existing
scheduler infrastructure this job plugs into (`main.py`'s leader-elected
asyncio loops) is itself a long-lived, single-process-per-lifetime
worker with no existing lightweight cross-restart state store for
anything like this (Redis here only backs short-TTL response caches,
e.g. `dashboard.scheduler.DashboardScheduler`'s view cache - not
scheduler position), so an in-memory cursor exactly matches
`AlertScheduler`'s own already-accepted restart semantics: a restart
resumes scanning from the start of the universe, never fails, never
loses correctness (every symbol is still eventually scanned), and adds
no new database table, migration, or Redis key.

No LLM is called anywhere in this module. No new decision/voting/risk
engine, no new database table, and no new scheduler/worker framework
are introduced - `run_once` is a synchronous, dependency-injected,
overlap-guarded unit of work meant to be driven by the existing
`main.py` leader-elected asyncio loop convention (see
`watchlist_scheduler.AlertScheduler`'s own `alert_scan_loop` for the
exact shape this plugs into).
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Protocol, runtime_checkable

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from intelligence.config import BackgroundIntelligenceConfig, IntelligenceConfig
from intelligence.models import BackgroundScanResult, BackgroundScanStatus, ScanSymbolStatus
from intelligence.opportunity_ranking import ScannerProtocol, rank_opportunities

logger = logging.getLogger(__name__)

_MODULE = "intelligence.background_intelligence"
_COMPONENT = "intelligence"


@runtime_checkable
class UniverseProviderProtocol(Protocol):
    """The only contract `BackgroundIntelligenceOrchestrator` depends on
    for "which symbols exist" - deliberately narrow so a test can inject
    a fake universe freely, and so this module never hardcodes a second
    copy of any symbol list."""

    def get_symbols(self) -> List[str]: ...


class MarketConfigUniverseProvider:
    """Wraps the repository's one existing multi-market symbol universe
    (`core.market_config.get_symbols_for_market`, backing BIST/US/CRYPTO
    today) rather than duplicating any symbol list. Bound to exactly one
    market per instance - two providers for two different markets never
    share symbols, by construction."""

    def __init__(self, market: str = "US") -> None:
        self.market = market.upper()

    def get_symbols(self) -> List[str]:
        from core.market_config import get_symbols_for_market

        return list(get_symbols_for_market(self.market).keys())


class BackgroundIntelligenceOrchestrator:
    """Read-only from the intelligence layer's perspective: the only
    write this triggers at all is whatever `PipelineService.run()`
    already does under its own existing contract (persisting a
    `DecisionOutput` via `decision_engine.repository`) - this module
    itself never writes to any repository, never touches a watchlist/portfolio,
    and never creates an alert."""

    def __init__(
        self,
        scanner: Optional[ScannerProtocol] = None,
        universe_provider: Optional[UniverseProviderProtocol] = None,
        config: Optional[BackgroundIntelligenceConfig] = None,
        intelligence_config: Optional[IntelligenceConfig] = None,
    ) -> None:
        self.config = config or BackgroundIntelligenceConfig.from_env()
        self.intelligence_config = intelligence_config or IntelligenceConfig.from_env()
        if scanner is None:
            from intelligence.market_scanner import MarketScanner

            scanner = MarketScanner()
        self.scanner = scanner
        self.universe_provider = universe_provider or MarketConfigUniverseProvider(self.config.market)
        # In-memory rotating cursor - see this module's own docstring for
        # why this matches `AlertScheduler._scan_offset`'s restart
        # semantics rather than introducing new persistent state.
        self._cursor = 0
        # Overlap guard: a non-blocking lock, mirroring
        # `AlertScheduler._in_flight`'s "skip rather than run twice"
        # philosophy. The leader-elected asyncio loop this is meant to
        # be driven by (one `await` per tick, never firing the next tick
        # until the previous one's executor call returns) already makes
        # overlap essentially impossible in production; this guard is
        # defense-in-depth for any other caller (a manual trigger, a
        # test) invoking `run_once` concurrently.
        self._run_lock = threading.Lock()

    def run_once(self) -> BackgroundScanResult:
        started_at = datetime.now(timezone.utc)
        execution_id = uuid.uuid4().hex

        if not self.config.enabled:
            return self._skip(execution_id, BackgroundScanStatus.SKIPPED_DISABLED, started_at)

        if not self._run_lock.acquire(blocking=False):
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="run_once", status=STATUS_SUCCESS,
                execution_id=execution_id, skipped="overlap",
            )
            return self._skip(execution_id, BackgroundScanStatus.SKIPPED_OVERLAP, started_at)
        try:
            return self._execute(execution_id, started_at)
        finally:
            self._run_lock.release()

    def _execute(self, execution_id: str, started_at: datetime) -> BackgroundScanResult:
        cursor_before = self._cursor

        try:
            universe = list(dict.fromkeys(self.universe_provider.get_symbols()))
        except Exception as exc:
            return self._failure(execution_id, started_at, cursor_before, cursor_before, exc)

        if not universe:
            return self._completed(execution_id, started_at, [], None, cursor_before=0, cursor_after=0)

        if cursor_before >= len(universe) or cursor_before < 0:
            cursor_before = 0

        batch_size = max(self.config.batch_size, 0)
        batch = universe[cursor_before:cursor_before + batch_size] if batch_size > 0 else []
        cursor_after = cursor_before + len(batch)
        if cursor_after >= len(universe):
            cursor_after = 0
        self._cursor = cursor_after

        if not batch:
            return self._completed(execution_id, started_at, [], None, cursor_before, cursor_after)

        try:
            scan_result = self.scanner.scan(batch)
        except Exception as exc:
            return self._failure(execution_id, started_at, cursor_before, cursor_after, exc, requested=batch)

        ranking = rank_opportunities(scan_result, self.intelligence_config)
        return self._completed(execution_id, started_at, batch, (scan_result, ranking), cursor_before, cursor_after)

    def _completed(
        self, execution_id: str, started_at: datetime, requested: List[str], outcome, cursor_before: int,
        cursor_after: int,
    ) -> BackgroundScanResult:
        successful_symbols: List[str] = []
        failed_symbols: List[str] = []
        timeout_symbols: List[str] = []
        ranking = None
        if outcome is not None:
            scan_result, ranking = outcome
            successful_symbols = [item.symbol for item in scan_result.successful]
            failed_symbols = [f.symbol for f in scan_result.failed if f.status == ScanSymbolStatus.FAILED]
            timeout_symbols = [f.symbol for f in scan_result.failed if f.status == ScanSymbolStatus.TIMEOUT]

        completed_at = datetime.now(timezone.utc)
        result = BackgroundScanResult(
            execution_id=execution_id, status=BackgroundScanStatus.COMPLETED,
            requested_symbols=requested, successful_symbols=successful_symbols, failed_symbols=failed_symbols,
            timeout_symbols=timeout_symbols, ranked_opportunities=ranking,
            started_at=started_at, completed_at=completed_at,
            duration_ms=(completed_at - started_at).total_seconds() * 1000,
            cursor_before=cursor_before, cursor_after=cursor_after,
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="run_once", status=STATUS_SUCCESS,
            execution_id=execution_id, requested_count=len(requested), successful_count=len(successful_symbols),
            failed_count=len(failed_symbols), timeout_count=len(timeout_symbols),
            cursor_before=cursor_before, cursor_after=cursor_after,
        )
        return result

    def _failure(
        self, execution_id: str, started_at: datetime, cursor_before: int, cursor_after: int, exc: Exception,
        requested: Optional[List[str]] = None,
    ) -> BackgroundScanResult:
        completed_at = datetime.now(timezone.utc)
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="run_once", status=STATUS_ERROR,
            execution_id=execution_id, error_type=type(exc).__name__, level=logging.ERROR,
        )
        return BackgroundScanResult(
            execution_id=execution_id, status=BackgroundScanStatus.FAILED,
            requested_symbols=requested or [], error_type=type(exc).__name__,
            started_at=started_at, completed_at=completed_at,
            duration_ms=(completed_at - started_at).total_seconds() * 1000,
            cursor_before=cursor_before, cursor_after=cursor_after,
        )

    def _skip(self, execution_id: str, status: BackgroundScanStatus, started_at: datetime) -> BackgroundScanResult:
        completed_at = datetime.now(timezone.utc)
        return BackgroundScanResult(
            execution_id=execution_id, status=status,
            started_at=started_at, completed_at=completed_at,
            duration_ms=(completed_at - started_at).total_seconds() * 1000,
            cursor_before=self._cursor, cursor_after=self._cursor,
        )

    def shutdown(self) -> None:
        """Mirrors `MarketScanner.shutdown()`/`AlertScheduler.shutdown()`
        - releases the underlying scanner's thread pool. Safe to call
        even if a tick never ran."""
        shutdown_fn = getattr(self.scanner, "shutdown", None)
        if callable(shutdown_fn):
            shutdown_fn()
