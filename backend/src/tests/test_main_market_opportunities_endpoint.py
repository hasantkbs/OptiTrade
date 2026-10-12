"""Tests for GET /market/opportunities/{market} - reads market_
opportunities_refresh_loop's cache only; never falls back to a live
scan (that would take far longer than any request should wait - see
the endpoint's own docstring in main.py)."""
import pytest

import main as main_module
from users.repository import UsersRepository

_EMAIL_PREFIX = "market-opps-test"


@pytest.fixture
def cleanup():
    yield
    users_repo = UsersRepository()
    with users_repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        user_ids = [row[0] for row in cur.fetchall()]
    if user_ids:
        with users_repo._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (user_ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (user_ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (user_ids,))


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register_and_login(client, name):
    client.post("/auth/register", json={"email": _email(name), "password": "MyPassw0rd1", "display_name": name})
    r = client.post("/auth/login", json={"email": _email(name), "password": "MyPassw0rd1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_requires_authentication(client, cleanup):
    assert client.get("/market/opportunities/US").status_code == 401


def test_rejects_an_unsupported_market(client, monkeypatch, cleanup):
    headers = _register_and_login(client, "unsupported")
    r = client.get("/market/opportunities/JP", headers=headers)
    assert r.status_code == 400


def test_returns_503_on_a_cold_cache(client, monkeypatch, cleanup):
    headers = _register_and_login(client, "cold")

    class _EmptyCache:
        def get(self, market):
            return None

    monkeypatch.setattr(main_module, "_opportunities_cache", _EmptyCache())
    r = client.get("/market/opportunities/US", headers=headers)
    assert r.status_code == 503


def test_returns_the_cached_ranking(client, monkeypatch, cleanup):
    headers = _register_and_login(client, "warm")
    payload = (
        '{"market": "US", "opportunities": [{"rank": 1, "symbol": "AAPL", "decision": "BUY", '
        '"label": "BUY_BIAS", "confidence": 0.8, "expected_return": 0.05, '
        '"expected_volatility": 0.2, "risk_bucket": "LOW"}], '
        '"total_scanned_count": 28, "failed_count": 0, "generated_at": "2026-01-01T00:00:00Z"}'
    )

    class _WarmCache:
        def get(self, market):
            return payload if market == "US" else None

    monkeypatch.setattr(main_module, "_opportunities_cache", _WarmCache())
    r = client.get("/market/opportunities/US", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["market"] == "US"
    assert len(body["opportunities"]) == 1
    assert body["opportunities"][0]["symbol"] == "AAPL"
    assert body["opportunities"][0]["label"] == "BUY_BIAS"


def test_market_is_case_insensitive(client, monkeypatch, cleanup):
    headers = _register_and_login(client, "lowercase")

    class _WarmCache:
        def get(self, market):
            assert market == "US"
            return (
                '{"market": "US", "opportunities": [], "total_scanned_count": 0, '
                '"failed_count": 0, "generated_at": "2026-01-01T00:00:00Z"}'
            )

    monkeypatch.setattr(main_module, "_opportunities_cache", _WarmCache())
    r = client.get("/market/opportunities/us", headers=headers)
    assert r.status_code == 200
