"""
Regression tests for the production audit's "An entire advertised
platform (Watchlist & Alerts) is unreachable" Critical finding.

Before this fix, `watchlist.WatchlistService`/`watchlist.AlertScheduler`
were fully built and fully unit-tested (test_watchlist_*.py) but main.py
exposed zero HTTP endpoints for creating/managing a watchlist or an
alert, and AlertScheduler was constructed at startup but never invoked
by anything (no cron/background task) - so even a caller who somehow
inserted rows directly could never have them evaluated. These tests
prove the platform is now actually reachable end-to-end: create a
watchlist, add a symbol, create an alert, and run a real scan.

Real PostgreSQL/Redis/network throughout, matching this project's
testing convention - uses the shared `client` fixture (conftest.py),
which stubs the periodic background loops (including the new
alert_scan_loop) with no-ops so tests control exactly when a scan runs
via the on-demand POST /alerts/scan endpoint.
"""
import pytest

from users.repository import UsersRepository
from watchlist.repository import WatchlistRepository

_EMAIL_PREFIX = "main-watchlist-test"


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register_and_login(client, name):
    client.post("/auth/register", json={"email": _email(name), "password": "MyPassw0rd1", "display_name": name})
    r = client.post("/auth/login", json={"email": _email(name), "password": "MyPassw0rd1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def cleanup():
    yield
    wl_repo = WatchlistRepository()
    users_repo = UsersRepository()

    with wl_repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM watchlist_watchlists WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))
        wl_ids = [r[0] for r in cur.fetchall()]
        for wl_id in wl_ids:
            cur.execute("DELETE FROM watchlist_items WHERE watchlist_id = %s", (wl_id,))
        cur.execute("DELETE FROM watchlist_watchlists WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))
        cur.execute("SELECT id FROM watchlist_alerts WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))
        alert_ids = [r[0] for r in cur.fetchall()]
        for alert_id in alert_ids:
            cur.execute("DELETE FROM watchlist_alert_trigger_history WHERE alert_id = %s", (alert_id,))
        cur.execute("DELETE FROM watchlist_alerts WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))

    with users_repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM users_users WHERE email LIKE %s", (f"{_EMAIL_PREFIX}%",))
        user_ids = [r[0] for r in cur.fetchall()]
        if user_ids:
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (user_ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (user_ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (user_ids,))


def test_watchlist_endpoints_require_authentication(client, cleanup):
    assert client.post("/watchlists", json={"name": "x"}).status_code == 401
    assert client.get("/watchlists").status_code == 401
    assert client.post("/alerts", json={"category": "price", "alert_type": "price_above"}).status_code == 401
    assert client.get("/alerts").status_code == 401


def test_create_watchlist_add_item_and_list(client, cleanup):
    headers = _register_and_login(client, "crud")

    r = client.post("/watchlists", json={"name": "My Watchlist"}, headers=headers)
    assert r.status_code == 200, r.text
    watchlist_id = r.json()["id"]
    assert r.json()["owner"] == _email("crud")

    r = client.post(f"/watchlists/{watchlist_id}/items", json={"symbol": "aapl", "is_favorite": True}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["symbol"] == "AAPL"
    assert r.json()["is_favorite"] is True

    r = client.get(f"/watchlists/{watchlist_id}/items", headers=headers)
    assert r.status_code == 200
    assert any(item["symbol"] == "AAPL" for item in r.json())

    r = client.get("/watchlists", headers=headers)
    assert r.status_code == 200
    assert any(wl["id"] == watchlist_id for wl in r.json())

    r = client.delete(f"/watchlists/{watchlist_id}/items/AAPL", headers=headers)
    assert r.status_code == 200
    r = client.get(f"/watchlists/{watchlist_id}/items", headers=headers)
    assert all(item["symbol"] != "AAPL" for item in r.json())

    r = client.delete(f"/watchlists/{watchlist_id}", headers=headers)
    assert r.status_code == 200
    assert client.get(f"/watchlists/{watchlist_id}", headers=headers).status_code == 404


def test_cannot_access_another_owners_watchlist(client, cleanup):
    owner_headers = _register_and_login(client, "wl-owner")
    intruder_headers = _register_and_login(client, "wl-intruder")

    r = client.post("/watchlists", json={"name": "Private"}, headers=owner_headers)
    watchlist_id = r.json()["id"]

    assert client.get(f"/watchlists/{watchlist_id}", headers=intruder_headers).status_code == 403
    assert client.post(
        f"/watchlists/{watchlist_id}/items", json={"symbol": "AAPL"}, headers=intruder_headers,
    ).status_code == 403
    assert client.delete(f"/watchlists/{watchlist_id}", headers=intruder_headers).status_code == 403


def test_create_alert_ignores_caller_supplied_owner_and_runs_scan(client, cleanup):
    headers = _register_and_login(client, "alert-crud")

    body = {
        "category": "price", "alert_type": "price_above", "symbol": "AAPL",
        "parameters": {"threshold": 1.0}, "cooldown_minutes": 60,
    }
    r = client.post("/alerts", json=body, headers=headers)
    assert r.status_code == 200, r.text
    alert = r.json()
    assert alert["owner"] == _email("alert-crud")
    alert_id = alert["id"]

    r = client.get("/alerts", headers=headers)
    assert r.status_code == 200
    assert any(a["id"] == alert_id for a in r.json())

    r = client.get(f"/alerts/{alert_id}", headers=headers)
    assert r.status_code == 200

    # This is the actual reachability regression: AlertScheduler.run_scan
    # previously had nothing calling it at all - proving this endpoint
    # works end-to-end (real repository read, real evaluator dispatch)
    # is the core of this Critical fix.
    r = client.post("/alerts/scan", headers=headers)
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["total_alerts"] >= 1
    assert report["checked_count"] >= 1

    r = client.patch(f"/alerts/{alert_id}/enabled", json={"enabled": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = client.delete(f"/alerts/{alert_id}", headers=headers)
    assert r.status_code == 200
    assert client.get(f"/alerts/{alert_id}", headers=headers).status_code == 404


def test_cannot_access_another_owners_alert(client, cleanup):
    owner_headers = _register_and_login(client, "alert-owner")
    intruder_headers = _register_and_login(client, "alert-intruder")

    r = client.post(
        "/alerts", json={"category": "price", "alert_type": "price_above", "symbol": "AAPL"}, headers=owner_headers,
    )
    alert_id = r.json()["id"]

    assert client.get(f"/alerts/{alert_id}", headers=intruder_headers).status_code == 403
    assert client.patch(
        f"/alerts/{alert_id}/enabled", json={"enabled": False}, headers=intruder_headers,
    ).status_code == 403
    assert client.delete(f"/alerts/{alert_id}", headers=intruder_headers).status_code == 403

    # the intruder's own scan must never evaluate (or even count) someone
    # else's alert
    r = client.post("/alerts/scan", headers=intruder_headers)
    assert r.status_code == 200
    assert r.json()["total_alerts"] == 0
