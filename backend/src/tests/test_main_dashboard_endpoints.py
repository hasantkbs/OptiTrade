"""Integration tests for the Analytics & Dashboard Platform endpoints
wired into main.py. Uses the shared `client` fixture (real main.app,
real startup, self-evolution loop stubbed - see conftest.py). Real
PostgreSQL/Redis/network throughout."""
import pytest

from paper_trading.repository import PaperTradingRepository
from portfolio.repository import PortfolioRepository
from users.repository import UsersRepository
from watchlist.repository import WatchlistRepository

_EMAIL_PREFIX = "main-dash-test"


@pytest.fixture
def cleanup():
    yield
    users_repo = UsersRepository()
    pt_repo = PaperTradingRepository()
    port_repo = PortfolioRepository()
    wl_repo = WatchlistRepository()

    with users_repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id, email FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        users = cur.fetchall()
    user_ids = [u[0] for u in users]
    emails = [u[1] for u in users]

    if user_ids:
        with pt_repo._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT id, portfolio_id FROM paper_trading_accounts WHERE user_id = ANY(%s)", (user_ids,))
            rows = cur.fetchall()
            account_ids = [r[0] for r in rows]
            portfolio_ids_pt = [r[1] for r in rows]
            if account_ids:
                cur.execute(
                    "DELETE FROM paper_trading_journal_entries WHERE account_id = ANY(%s)", (account_ids,),
                )
                cur.execute("DELETE FROM paper_trading_fills WHERE account_id = ANY(%s)", (account_ids,))
                cur.execute("DELETE FROM paper_trading_orders WHERE account_id = ANY(%s)", (account_ids,))
                cur.execute("DELETE FROM paper_trading_accounts WHERE id = ANY(%s)", (account_ids,))
        with port_repo._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM portfolio_portfolios WHERE owner = ANY(%s)", (emails,))
            portfolio_ids = list(set([r[0] for r in cur.fetchall()] + portfolio_ids_pt))
            if portfolio_ids:
                cur.execute("DELETE FROM portfolio_snapshots WHERE portfolio_id = ANY(%s)", (portfolio_ids,))
                cur.execute("DELETE FROM portfolio_transactions WHERE portfolio_id = ANY(%s)", (portfolio_ids,))
                cur.execute("DELETE FROM portfolio_portfolios WHERE id = ANY(%s)", (portfolio_ids,))
        with wl_repo._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM watchlist_watchlists WHERE owner = ANY(%s)", (emails,))
            wl_ids = [r[0] for r in cur.fetchall()]
            for wl_id in wl_ids:
                cur.execute("DELETE FROM watchlist_items WHERE watchlist_id = %s", (wl_id,))
            cur.execute("DELETE FROM watchlist_watchlists WHERE owner = ANY(%s)", (emails,))
            cur.execute("DELETE FROM watchlist_alerts WHERE owner = ANY(%s)", (emails,))
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


def test_dashboard_requires_authentication(client, cleanup):
    assert client.get("/dashboard/overview").status_code == 401
    assert client.get("/dashboard/engines").status_code == 401
    assert client.get("/dashboard/ml").status_code == 401
    assert client.get("/dashboard/watchlists").status_code == 401
    assert client.get("/dashboard/learning").status_code == 401
    assert client.get("/dashboard/alerts").status_code == 401
    assert client.get("/dashboard/market").status_code == 401
    assert client.get("/dashboard/reports/daily").status_code == 401


def test_overview_endpoint(client, cleanup):
    headers = _register_and_login(client, "overview")
    r = client.get("/dashboard/overview", headers=headers)
    assert r.status_code == 200
    assert r.json()["total_users"] >= 1


def test_engines_endpoint(client, cleanup):
    headers = _register_and_login(client, "engines")
    r = client.get("/dashboard/engines?regime_symbols=AAPL&regime_symbols=MSFT", headers=headers)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["engines"], list)


def test_ml_endpoint(client, cleanup):
    headers = _register_and_login(client, "ml")
    r = client.get("/dashboard/ml", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json()["registry_entries"], list)


def test_watchlists_endpoint(client, cleanup):
    headers = _register_and_login(client, "watchlists")
    r = client.get("/dashboard/watchlists", headers=headers)
    assert r.status_code == 200
    assert r.json()["total_watchlists"] == 0


def test_learning_endpoint(client, cleanup):
    headers = _register_and_login(client, "learning")
    r = client.get("/dashboard/learning", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json()["engine_rankings"], list)


def test_alerts_endpoint(client, cleanup):
    headers = _register_and_login(client, "alerts")
    r = client.get("/dashboard/alerts", headers=headers)
    assert r.status_code == 200
    assert r.json()["active_alerts"] == 0


def test_market_endpoint(client, cleanup):
    headers = _register_and_login(client, "market")
    r = client.get("/dashboard/market?symbols=AAPL&market=US", headers=headers)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["regime_distribution"], dict)


def test_reports_endpoint_json_and_csv(client, cleanup):
    headers = _register_and_login(client, "reports")
    r = client.get("/dashboard/reports/monthly", headers=headers)
    assert r.status_code == 200, r.text
    assert "summary" in r.json()

    r = client.get("/dashboard/reports/monthly?format=csv", headers=headers)
    assert r.status_code == 200
    assert "metric,value" in r.text


def test_portfolio_dashboard_endpoint_and_ownership(client, cleanup):
    headers = _register_and_login(client, "portfolio")
    other_headers = _register_and_login(client, "portfolio-intruder")

    r = client.post("/portfolios", json={"owner": _email("portfolio"), "name": "Dash Test Portfolio"}, headers=headers)
    assert r.status_code == 200, r.text
    portfolio_id = r.json()["id"]
    client.post(f"/portfolios/{portfolio_id}/deposit", json={"amount": 10000.0}, headers=headers)

    r = client.get(f"/dashboard/portfolios/{portfolio_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["dashboard"]["total_value"] > 0

    r = client.get(f"/dashboard/portfolios/{portfolio_id}", headers=other_headers)
    assert r.status_code == 403

    r = client.get("/dashboard/portfolios/999999999", headers=headers)
    assert r.status_code == 404


def test_paper_trading_dashboard_endpoint_and_ownership(client, cleanup):
    headers = _register_and_login(client, "papertrading")
    other_headers = _register_and_login(client, "papertrading-intruder")

    r = client.post("/paper-trading/accounts", json={"starting_balance": 20000.0}, headers=headers)
    assert r.status_code == 200, r.text
    account_id = r.json()["id"]

    r = client.get(f"/dashboard/paper-trading/{account_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert "journal_statistics" in r.json()

    r = client.get(f"/dashboard/paper-trading/{account_id}", headers=other_headers)
    assert r.status_code == 403

    r = client.get("/dashboard/paper-trading/999999999", headers=headers)
    assert r.status_code == 404
