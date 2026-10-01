"""Tests for watchlist/scheduler.py. Real PostgreSQL for alert
persistence/state; a fake, fully-controllable `alert_engine` so retry/
timeout/failure paths are deterministic and fast rather than depending
on real external flakiness."""
import time

import pytest

from watchlist.config import WatchlistConfig
from watchlist.exceptions import InsufficientAlertDataError
from watchlist.models import Alert, AlertCategory, AlertCheckStatus, AlertTriggerEvent, AlertType
from watchlist.notification_router import InMemoryNotificationProvider, NotificationRouter
from watchlist.repository import WatchlistRepository
from watchlist.scheduler import AlertScheduler

_OWNER_PREFIX = "wl-scheduler-test-owner"


class _FakeAlertEngine:
    def __init__(self, behavior):
        self.behavior = behavior
        self.call_count = 0

    def evaluate(self, alert):
        self.call_count += 1
        return self.behavior(alert)


@pytest.fixture
def repository():
    repo = WatchlistRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM watchlist_alert_trigger_history WHERE alert_id IN "
                "(SELECT id FROM watchlist_alerts WHERE owner LIKE %s)", (f"{_OWNER_PREFIX}%",),
            )
            cur.execute("DELETE FROM watchlist_alerts WHERE owner LIKE %s", (f"{_OWNER_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


def _save_alert(repository, owner_suffix, cooldown_minutes=60):
    alert = Alert(
        owner=f"{_OWNER_PREFIX}-{owner_suffix}", symbol="AAPL", category=AlertCategory.PRICE,
        alert_type=AlertType.PRICE_ABOVE, parameters={"threshold": 1.0}, cooldown_minutes=cooldown_minutes,
    )
    alert.id = repository.save_alert(alert)
    return alert


def _scheduler(repository, engine, config=None):
    config = config or WatchlistConfig(min_check_interval_seconds=0, max_parallel_workers=4, max_retries=1, alert_timeout_seconds=1.0)
    provider = InMemoryNotificationProvider()
    router = NotificationRouter(providers=[provider], config=config)
    scheduler = AlertScheduler(repository=repository, alert_engine=engine, notification_router=router, config=config)
    return scheduler, provider


def test_triggered_alert_is_notified_and_persisted(repository):
    alert = _save_alert(repository, "triggered")

    def behavior(a):
        event = AlertTriggerEvent(
            alert_id=a.id, owner=a.owner, symbol=a.symbol, category=a.category, alert_type=a.alert_type,
            message="fired", evidence={"price": 210.0},
        )
        return event, {"last_price": 210.0}

    scheduler, provider = _scheduler(repository, _FakeAlertEngine(behavior))
    report = scheduler.run_scan(owner=alert.owner)

    assert report.triggered_count == 1
    assert report.outcomes[0].status == AlertCheckStatus.TRIGGERED
    assert len(provider.sent) == 1

    refreshed = repository.get_alert(alert.id)
    assert refreshed.last_triggered_at is not None
    assert refreshed.last_state == {"last_price": 210.0}
    assert len(repository.list_triggers(alert.id)) == 1
    scheduler.shutdown()


def test_not_triggered_alert_updates_state_without_notifying(repository):
    alert = _save_alert(repository, "not-triggered")

    def behavior(a):
        return None, {"last_price": 100.0}

    scheduler, provider = _scheduler(repository, _FakeAlertEngine(behavior))
    report = scheduler.run_scan(owner=alert.owner)

    assert report.triggered_count == 0
    assert report.outcomes[0].status == AlertCheckStatus.NOT_TRIGGERED
    assert len(provider.sent) == 0
    refreshed = repository.get_alert(alert.id)
    assert refreshed.last_state == {"last_price": 100.0}
    assert refreshed.last_triggered_at is None
    scheduler.shutdown()


def test_cooldown_suppresses_a_second_notification(repository):
    alert = _save_alert(repository, "cooldown", cooldown_minutes=60)

    def behavior(a):
        event = AlertTriggerEvent(
            alert_id=a.id, owner=a.owner, symbol=a.symbol, category=a.category, alert_type=a.alert_type,
            message="fired", evidence={},
        )
        return event, {}

    scheduler, provider = _scheduler(repository, _FakeAlertEngine(behavior))
    scheduler.run_scan(owner=alert.owner)
    assert len(provider.sent) == 1

    report2 = scheduler.run_scan(owner=alert.owner)
    assert report2.outcomes[0].status == AlertCheckStatus.SKIPPED_COOLDOWN
    assert len(provider.sent) == 1  # unchanged - no second notification
    scheduler.shutdown()


def test_incremental_scanning_skips_alerts_not_yet_due(repository):
    alert = _save_alert(repository, "incremental")
    config = WatchlistConfig(min_check_interval_seconds=3600, max_parallel_workers=4)
    engine = _FakeAlertEngine(lambda a: (None, {}))
    scheduler, _ = _scheduler(repository, engine, config=config)

    report1 = scheduler.run_scan(owner=alert.owner)
    assert report1.checked_count == 1

    report2 = scheduler.run_scan(owner=alert.owner)
    assert report2.checked_count == 0
    assert engine.call_count == 1
    scheduler.shutdown()


def test_timeout_is_retried_and_reported(repository):
    alert = _save_alert(repository, "timeout")
    config = WatchlistConfig(min_check_interval_seconds=0, max_parallel_workers=4, max_retries=1, alert_timeout_seconds=0.2)

    def behavior(a):
        time.sleep(1.0)
        return None, {}

    scheduler, _ = _scheduler(repository, _FakeAlertEngine(behavior), config=config)
    report = scheduler.run_scan(owner=alert.owner)
    assert report.outcomes[0].status == AlertCheckStatus.TIMEOUT
    assert report.outcomes[0].attempts == 2  # 1 initial + 1 retry
    scheduler.shutdown()


def test_transient_failure_is_retried_then_succeeds(repository):
    alert = _save_alert(repository, "retry-success")
    config = WatchlistConfig(min_check_interval_seconds=0, max_parallel_workers=4, max_retries=2, alert_timeout_seconds=2.0)
    attempts = {"count": 0}

    def behavior(a):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient")
        return None, {"ok": 1.0}

    scheduler, _ = _scheduler(repository, _FakeAlertEngine(behavior), config=config)
    report = scheduler.run_scan(owner=alert.owner)
    assert report.outcomes[0].status == AlertCheckStatus.NOT_TRIGGERED
    assert report.outcomes[0].attempts == 2
    scheduler.shutdown()


def test_permanent_failure_is_reported_after_exhausting_retries(repository):
    alert = _save_alert(repository, "permanent-failure")
    config = WatchlistConfig(min_check_interval_seconds=0, max_parallel_workers=4, max_retries=1, alert_timeout_seconds=2.0)

    def behavior(a):
        raise RuntimeError("always fails")

    scheduler, _ = _scheduler(repository, _FakeAlertEngine(behavior), config=config)
    report = scheduler.run_scan(owner=alert.owner)
    assert report.outcomes[0].status == AlertCheckStatus.FAILED
    assert report.outcomes[0].error_type == "RuntimeError"
    assert report.outcomes[0].attempts == 2
    scheduler.shutdown()


def test_insufficient_data_error_is_not_retried(repository):
    alert = _save_alert(repository, "insufficient-data")
    config = WatchlistConfig(min_check_interval_seconds=0, max_parallel_workers=4, max_retries=2, alert_timeout_seconds=2.0)

    def behavior(a):
        raise InsufficientAlertDataError("no data yet")

    engine = _FakeAlertEngine(behavior)
    scheduler, _ = _scheduler(repository, engine, config=config)
    report = scheduler.run_scan(owner=alert.owner)
    assert report.outcomes[0].status == AlertCheckStatus.FAILED
    assert report.outcomes[0].attempts == 1  # no retry for a permanent-for-now condition
    assert engine.call_count == 1
    scheduler.shutdown()


def test_deduplication_skips_an_alert_already_in_flight(repository):
    alert = _save_alert(repository, "dedup")
    scheduler, _ = _scheduler(repository, _FakeAlertEngine(lambda a: (None, {})))
    scheduler._in_flight.add(alert.id)
    try:
        outcome = scheduler._check_one_deduped(repository.get_alert(alert.id))
        assert outcome.status == AlertCheckStatus.SKIPPED_DEDUP
    finally:
        scheduler._in_flight.discard(alert.id)
        scheduler.shutdown()


def test_run_scan_processes_multiple_alerts_in_parallel(repository):
    owner = f"{_OWNER_PREFIX}-parallel-shared"
    alerts = []
    for i in range(5):
        alert = Alert(
            owner=owner, symbol=f"SYM{i}", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE,
            parameters={"threshold": 1.0},
        )
        alert.id = repository.save_alert(alert)
        alerts.append(alert)

    engine = _FakeAlertEngine(lambda a: (None, {}))
    scheduler, _ = _scheduler(repository, engine)
    report = scheduler.run_scan(owner=owner)
    assert report.checked_count == 5
    assert engine.call_count == 5
    scheduler.shutdown()


def test_disabled_alerts_are_never_scanned(repository):
    alert = _save_alert(repository, "disabled")
    repository.set_alert_enabled(alert.id, False)
    engine = _FakeAlertEngine(lambda a: (None, {}))
    scheduler, _ = _scheduler(repository, engine)
    report = scheduler.run_scan(owner=alert.owner)
    assert report.total_alerts == 0
    scheduler.shutdown()


def test_service_defaults_to_real_dependencies():
    scheduler = AlertScheduler()
    assert isinstance(scheduler.repository, WatchlistRepository)
    scheduler.shutdown()


# ─────────────────────────────────────────────────────────────────────────
# Global-sweep pagination regression (production audit HIGH #5: "Once
# more than 200 enabled alerts exist, newer alerts are never scanned").
# owner=None (the periodic global sweep alert_scan_loop drives, as
# opposed to every other test above's owner-scoped on-demand scan) must
# rotate through the full enabled-alert set across successive calls
# rather than being permanently capped to the first `scan_batch_size`
# alerts that ever existed.
# ─────────────────────────────────────────────────────────────────────────

def test_global_scan_rotates_through_more_alerts_than_one_batch(repository):
    config = WatchlistConfig(
        min_check_interval_seconds=0, max_parallel_workers=4, max_retries=0, alert_timeout_seconds=1.0,
        scan_batch_size=5,
    )
    owner = f"{_OWNER_PREFIX}-rotation"
    created_ids = set()
    for i in range(12):  # more than 2x the 5-alert batch size
        alert = Alert(
            owner=owner, symbol=f"ROT{i}", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE,
            parameters={"threshold": 1.0},
        )
        alert.id = repository.save_alert(alert)
        created_ids.add(alert.id)

    engine = _FakeAlertEngine(lambda a: (None, {}))
    scheduler, _ = _scheduler(repository, engine, config=config)

    seen_ids = set()
    try:
        # ceil(12/5) = 3 ticks is the theoretical minimum to cover every
        # alert once - run double that for headroom against any other
        # enabled alerts sharing the same global rotation.
        for _ in range(6):
            report = scheduler.run_scan()  # owner=None - the global sweep, not owner-scoped
            seen_ids.update(outcome.alert_id for outcome in report.outcomes)

        assert created_ids <= seen_ids, (
            f"never scanned: {created_ids - seen_ids} - the global sweep must eventually reach every alert"
        )
    finally:
        scheduler.shutdown()


def test_global_scan_batch_is_bounded_to_the_configured_batch_size(repository):
    config = WatchlistConfig(
        min_check_interval_seconds=0, max_parallel_workers=4, max_retries=0, alert_timeout_seconds=1.0,
        scan_batch_size=5,
    )
    owner = f"{_OWNER_PREFIX}-bounded"
    for i in range(12):
        alert = Alert(
            owner=owner, symbol=f"BND{i}", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE,
            parameters={"threshold": 1.0},
        )
        alert.id = repository.save_alert(alert)

    engine = _FakeAlertEngine(lambda a: (None, {}))
    scheduler, _ = _scheduler(repository, engine, config=config)
    try:
        # A single tick must never load more than scan_batch_size alerts
        # - the periodic sweep's whole point is bounded, predictable
        # per-tick cost, not "eventually load everything in one call".
        report = scheduler.run_scan()
        assert report.total_alerts <= config.scan_batch_size
    finally:
        scheduler.shutdown()
