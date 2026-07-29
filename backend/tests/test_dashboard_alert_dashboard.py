"""Tests for dashboard/alert_dashboard.py. Real PostgreSQL throughout."""
from datetime import datetime, timedelta, timezone

import pytest

from dashboard.alert_dashboard import AlertDashboardService
from dashboard.repository import DashboardRepository
from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.repository import WatchlistRepository

_OWNER_PREFIX = "dash-alert-test-owner"


@pytest.fixture
def watchlist_repo():
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


@pytest.fixture
def dashboard_repo():
    repository = DashboardRepository()
    yield repository
    repository.close()


@pytest.fixture
def service(dashboard_repo, watchlist_repo):
    return AlertDashboardService(dashboard_repo, watchlist_repository=watchlist_repo)


def _owner(name: str) -> str:
    return f"{_OWNER_PREFIX}-{name}"


def test_build_empty_for_unknown_owner(service):
    view = service.build("nobody@example.com")
    assert view.active_alerts == 0
    assert view.fired_last_24h == 0


def test_active_alerts_count(service, watchlist_repo):
    owner = _owner("active")
    watchlist_repo.save_alert(Alert(owner=owner, symbol="AAPL", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE, parameters={"threshold": 100.0}))
    watchlist_repo.save_alert(Alert(owner=owner, symbol="MSFT", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_BELOW, parameters={"threshold": 50.0}, enabled=False))

    view = service.build(owner)
    assert view.active_alerts == 1


def test_recently_fired_and_trigger_frequency(service, watchlist_repo):
    owner = _owner("fired")
    alert_id = watchlist_repo.save_alert(Alert(owner=owner, symbol="AAPL", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE, parameters={"threshold": 100.0}))
    now = datetime.now(timezone.utc)
    watchlist_repo.save_trigger(alert_id, now, "Crossed above 100", {"price": 105.0})
    watchlist_repo.save_trigger(alert_id, now - timedelta(hours=1), "Crossed above 100 again", {"price": 106.0})

    view = service.build(owner)
    assert view.fired_last_24h == 2
    assert len(view.recently_fired) == 2
    assert view.recently_fired[0].symbol == "AAPL"
    assert view.trigger_frequency_by_type == {"price_above": 2}


def test_scoping_by_owner_excludes_other_owners_triggers(service, watchlist_repo):
    owner_a = _owner("scoped-a")
    owner_b = _owner("scoped-b")
    alert_a = watchlist_repo.save_alert(Alert(owner=owner_a, symbol="AAPL", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE, parameters={"threshold": 100.0}))
    alert_b = watchlist_repo.save_alert(Alert(owner=owner_b, symbol="MSFT", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE, parameters={"threshold": 200.0}))
    now = datetime.now(timezone.utc)
    watchlist_repo.save_trigger(alert_a, now, "A fired", {})
    watchlist_repo.save_trigger(alert_b, now, "B fired", {})

    view = service.build(owner_a)
    assert view.fired_last_24h == 1
    assert view.recently_fired[0].alert_id == alert_a
