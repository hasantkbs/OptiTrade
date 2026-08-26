"""
OptiTrade Watchlist & Alert Platform — Alert Scheduler.

Mirrors `pipeline.executor.ParallelEngineExecutor`'s established
"thread pool + per-attempt timeout + bounded retry, never raises"
shape, applied to alert evaluation instead of engine voting:

  - incremental scanning: only alerts due for a check
    (`last_checked_at` older than `min_check_interval_seconds`, or
    never checked) are evaluated at all.
  - parallel execution: every due alert is submitted to a shared
    thread pool.
  - retry: transient failures (anything except `InsufficientAlertDataError`/
    `InvalidAlertError`, which retrying can never fix) get up to
    `max_retries` extra attempts.
  - timeouts: each attempt is bounded by `alert_timeout_seconds`,
    exactly like `pipeline.executor._call_with_timeout`.
  - deduplication: an alert already being evaluated (an overlapping
    scan, e.g. a slow previous run still in flight) is skipped rather
    than evaluated twice concurrently.
  - cooldown: a triggered alert whose own `cooldown_minutes` hasn't
    elapsed since it last fired is not re-notified, though its
    `last_state`/`last_checked_at` are still updated.

Every outcome (triggered, not triggered, skipped, timed out, failed) is
captured in the returned `ScanReport` - a single bad alert can never
abort the scan.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from typing import List, Optional, Set

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from watchlist.alert_engine import AlertEngine
from watchlist.config import WatchlistConfig
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCheckOutcome, AlertCheckStatus, ScanReport
from watchlist.notification_router import NotificationRouter
from watchlist.repository import WatchlistRepository

logger = logging.getLogger(__name__)


def _call_with_timeout(func, timeout_seconds: float):
    """See `pipeline.executor._call_with_timeout`'s identical rationale:
    `shutdown(wait=False)` lets this return as soon as the timeout
    elapses rather than blocking on an abandoned, still-running call."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False)


class AlertScheduler:
    def __init__(
        self,
        repository: Optional[WatchlistRepository] = None,
        alert_engine: Optional[AlertEngine] = None,
        notification_router: Optional[NotificationRouter] = None,
        config: Optional[WatchlistConfig] = None,
    ) -> None:
        self.config = config or WatchlistConfig.from_env()
        self.repository = repository or WatchlistRepository()
        self.alert_engine = alert_engine or AlertEngine(config=self.config)
        self.notification_router = notification_router or NotificationRouter(config=self.config)
        self._pool = ThreadPoolExecutor(max_workers=self.config.max_parallel_workers)
        self._in_flight: Set[int] = set()
        self._in_flight_lock = threading.Lock()
        # Rotating cursor for the global sweep (owner=None) only - see
        # run_scan below. Never reset for an owner-scoped scan, so the
        # periodic sweep's rotation isn't disturbed by an on-demand
        # single-owner call landing in between two ticks.
        self._scan_offset = 0

    def run_scan(self, owner: Optional[str] = None) -> ScanReport:
        """Owner-scoped calls (the on-demand `POST /alerts/scan`
        endpoint) load that owner's entire enabled-alert set in one
        page - naturally bounded by how many alerts one owner can have.

        The periodic global sweep (`owner=None`, called every
        `alert_scan_loop` tick) instead loads ONE bounded page
        (`scan_batch_size` alerts) per call and advances an internal
        offset, rotating through the full enabled-alert set across
        successive ticks rather than ever being capped to only the
        first `scan_batch_size` alerts that ever existed (production
        audit HIGH #5) - every enabled alert is still eventually
        scanned, without loading an unbounded number of alerts into
        memory or slowing down any single tick."""
        scan_started_at = time.perf_counter()
        started_dt = datetime.now(timezone.utc)

        if owner is not None:
            all_alerts = self.repository.list_alerts(owner=owner, enabled_only=True, limit=self.config.scan_batch_size)
        else:
            total_enabled = self.repository.count_alerts(enabled_only=True)
            if total_enabled == 0 or self._scan_offset >= total_enabled:
                self._scan_offset = 0
            all_alerts = self.repository.list_alerts(
                enabled_only=True, limit=self.config.scan_batch_size, offset=self._scan_offset,
            )
            self._scan_offset += len(all_alerts)

        due_alerts = [alert for alert in all_alerts if self._is_due(alert)]

        futures = [self._pool.submit(self._check_one_deduped, alert) for alert in due_alerts]
        outcomes: List[AlertCheckOutcome] = [future.result() for future in futures]

        triggered_count = sum(1 for outcome in outcomes if outcome.status == AlertCheckStatus.TRIGGERED)
        duration_ms = (time.perf_counter() - scan_started_at) * 1000
        report = ScanReport(
            started_at=started_dt, total_alerts=len(all_alerts), checked_count=len(due_alerts),
            triggered_count=triggered_count, outcomes=outcomes, duration_ms=duration_ms,
        )
        log_event(
            logger, component="watchlist", module="watchlist.scheduler", operation="run_scan",
            status=STATUS_SUCCESS, total_alerts=report.total_alerts, checked_count=report.checked_count,
            triggered_count=report.triggered_count, execution_time_ms=duration_ms,
        )
        return report

    def _is_due(self, alert: Alert) -> bool:
        if alert.last_checked_at is None:
            return True
        elapsed = (datetime.now(timezone.utc) - alert.last_checked_at).total_seconds()
        return elapsed >= self.config.min_check_interval_seconds

    def _in_cooldown(self, alert: Alert) -> bool:
        if alert.last_triggered_at is None:
            return False
        elapsed = (datetime.now(timezone.utc) - alert.last_triggered_at).total_seconds()
        return elapsed < alert.cooldown_minutes * 60

    def _check_one_deduped(self, alert: Alert) -> AlertCheckOutcome:
        with self._in_flight_lock:
            if alert.id in self._in_flight:
                return AlertCheckOutcome(alert_id=alert.id, status=AlertCheckStatus.SKIPPED_DEDUP, duration_ms=0.0, attempts=0)
            self._in_flight.add(alert.id)
        try:
            return self._check_one(alert)
        finally:
            with self._in_flight_lock:
                self._in_flight.discard(alert.id)

    def _check_one(self, alert: Alert) -> AlertCheckOutcome:
        started_at = time.perf_counter()
        total_attempts = self.config.max_retries + 1
        last_error_type: Optional[str] = None

        for attempt in range(1, total_attempts + 1):
            try:
                trigger_event, new_state = _call_with_timeout(
                    lambda: self.alert_engine.evaluate(alert), self.config.alert_timeout_seconds,
                )
                return self._finalize(alert, trigger_event, new_state, started_at, attempt)
            except FutureTimeoutError:
                last_error_type = "TimeoutError"
                self._log_attempt(alert, attempt, STATUS_ERROR, last_error_type)
                continue
            except (InsufficientAlertDataError, InvalidAlertError) as exc:
                # Not transient - retrying won't help; skip this scan
                # cycle, but still record that we checked.
                self._log_attempt(alert, attempt, STATUS_ERROR, type(exc).__name__)
                self.repository.update_alert_state(
                    alert.id, alert.last_state, datetime.now(timezone.utc), alert.last_triggered_at,
                )
                return AlertCheckOutcome(
                    alert_id=alert.id, status=AlertCheckStatus.FAILED,
                    duration_ms=(time.perf_counter() - started_at) * 1000, attempts=attempt,
                    error_type=type(exc).__name__,
                )
            except Exception as exc:
                last_error_type = type(exc).__name__
                self._log_attempt(alert, attempt, STATUS_ERROR, last_error_type)
                continue

        status = AlertCheckStatus.TIMEOUT if last_error_type == "TimeoutError" else AlertCheckStatus.FAILED
        return AlertCheckOutcome(
            alert_id=alert.id, status=status, duration_ms=(time.perf_counter() - started_at) * 1000,
            attempts=total_attempts, error_type=last_error_type,
        )

    def _finalize(self, alert: Alert, trigger_event, new_state, started_at: float, attempt: int) -> AlertCheckOutcome:
        now = datetime.now(timezone.utc)
        duration_ms = (time.perf_counter() - started_at) * 1000

        if trigger_event is None:
            self.repository.update_alert_state(alert.id, new_state, now, alert.last_triggered_at)
            return AlertCheckOutcome(
                alert_id=alert.id, status=AlertCheckStatus.NOT_TRIGGERED, duration_ms=duration_ms, attempts=attempt,
            )

        if self._in_cooldown(alert):
            self.repository.update_alert_state(alert.id, new_state, now, alert.last_triggered_at)
            return AlertCheckOutcome(
                alert_id=alert.id, status=AlertCheckStatus.SKIPPED_COOLDOWN, duration_ms=duration_ms,
                attempts=attempt,
            )

        self.repository.save_trigger(alert.id, now, trigger_event.message, trigger_event.evidence)
        self.notification_router.route(trigger_event)
        self.repository.update_alert_state(alert.id, new_state, now, now)
        return AlertCheckOutcome(
            alert_id=alert.id, status=AlertCheckStatus.TRIGGERED, duration_ms=duration_ms, attempts=attempt,
            trigger_event=trigger_event,
        )

    @staticmethod
    def _log_attempt(alert: Alert, attempt: int, status: str, error_type: Optional[str]) -> None:
        log_event(
            logger, component="watchlist", module="watchlist.scheduler", operation="check_alert",
            status=status, alert_id=alert.id, attempt=attempt, error_type=error_type,
            level=logging.WARNING if status == STATUS_ERROR else logging.INFO,
        )

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)
