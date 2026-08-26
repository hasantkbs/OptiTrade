"""Integration tests for the Paper Trading & Trade Journal Platform
endpoints wired into main.py. Uses the shared `client` fixture (real
main.app, real startup, self-evolution loop stubbed - see conftest.py).
Real PostgreSQL/Redis throughout, real network for the underlying
Pipeline (BTC-USD is used for market orders to keep this deterministic
and inexpensive)."""
import pytest

from decision_engine.repository import PostgresExecutionRepository
from feature_store.config import FeatureStoreConfig
from learning.persistence import LearningRepository
from paper_trading.repository import PaperTradingRepository
from portfolio.repository import PortfolioRepository
from users.repository import UsersRepository
from watchlist.repository import WatchlistRepository

_EMAIL_PREFIX = "main-pt-test"
_TRADED_SYMBOLS = ("BTC-USD", "ETH-USD")


def _cleanup_pipeline_side_effects() -> None:
    """Every order placed in this test file - filled or resting -
    journals a real `pipeline.service.PipelineService.run()` call
    (requirement: trade journal captures the real decision) - that
    persists a real `decision_engine_executions` row and a real
    Continuous Learning `learning_samples` row for each traded symbol,
    exactly like `/quant/analyze` already does (see
    test_main_quant_endpoint.py's own identical cleanup)."""
    exec_repo = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    conn = exec_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            for symbol in _TRADED_SYMBOLS:
                cur.execute(
                    "DELETE FROM decision_engine_executions WHERE symbol = %s AND aggregation_strategy_version = %s",
                    (symbol, "pipeline_parallel_v1"),
                )
    finally:
        exec_repo._pool.putconn(conn)
    exec_repo.close()

    learning_repo = LearningRepository()
    conn2 = learning_repo._pool.getconn()
    try:
        with conn2, conn2.cursor() as cur:
            for symbol in _TRADED_SYMBOLS:
                cur.execute(
                    "DELETE FROM learning_samples WHERE symbol = %s AND decided_at > now() - interval '10 minutes'",
                    (symbol,),
                )
    finally:
        learning_repo._pool.putconn(conn2)


@pytest.fixture
def cleanup():
    yield
    _cleanup_pipeline_side_effects()
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
            portfolio_ids = [r[1] for r in rows]
            if account_ids:
                cur.execute(
                    "DELETE FROM paper_trading_screenshots WHERE journal_entry_id IN "
                    "(SELECT id FROM paper_trading_journal_entries WHERE account_id = ANY(%s))", (account_ids,),
                )
                cur.execute("DELETE FROM paper_trading_journal_entries WHERE account_id = ANY(%s)", (account_ids,))
                cur.execute("DELETE FROM paper_trading_fills WHERE account_id = ANY(%s)", (account_ids,))
                cur.execute("DELETE FROM paper_trading_orders WHERE account_id = ANY(%s)", (account_ids,))
                cur.execute("DELETE FROM paper_trading_accounts WHERE id = ANY(%s)", (account_ids,))
        with port_repo._connection() as conn, conn, conn.cursor() as cur:
            if portfolio_ids:
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
    pt_repo.close()
    users_repo.close()


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register_and_login(client, name):
    client.post("/auth/register", json={"email": _email(name), "password": "MyPassw0rd1", "display_name": name})
    r = client.post("/auth/login", json={"email": _email(name), "password": "MyPassw0rd1"})
    tokens = r.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_paper_trading_requires_authentication(client, cleanup):
    assert client.get("/paper-trading/accounts").status_code == 401
    assert client.post("/paper-trading/accounts", json={"name": "X"}).status_code == 401


def test_create_and_list_accounts(client, cleanup):
    headers = _register_and_login(client, "create")
    r = client.post("/paper-trading/accounts", json={"name": "My Account", "starting_balance": 75000.0}, headers=headers)
    assert r.status_code == 200, r.text
    account = r.json()
    assert account["starting_balance"] == 75000.0

    r = client.get("/paper-trading/accounts", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.get(f"/paper-trading/accounts/{account['id']}", headers=headers)
    assert r.status_code == 200


def test_get_unknown_account_returns_404(client, cleanup):
    headers = _register_and_login(client, "unknown")
    r = client.get("/paper-trading/accounts/999999999", headers=headers)
    assert r.status_code == 404


def test_market_order_lifecycle_and_journal(client, cleanup):
    headers = _register_and_login(client, "market")
    account = client.post("/paper-trading/accounts", json={"starting_balance": 200000.0}, headers=headers).json()
    account_id = account["id"]

    r = client.post(
        f"/paper-trading/accounts/{account_id}/orders",
        json={"symbol": "BTC-USD", "side": "buy", "order_type": "market", "quantity": 0.2},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    order = r.json()
    assert order["status"] == "filled"
    order_id = order["id"]

    r = client.get(f"/paper-trading/orders/{order_id}", headers=headers)
    assert r.status_code == 200

    r = client.get(f"/paper-trading/accounts/{account_id}/positions", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.get(f"/paper-trading/accounts/{account_id}/cash", headers=headers)
    assert r.status_code == 200 and r.json()["cash_balance"] < 200000.0

    r = client.get(f"/paper-trading/accounts/{account_id}/total-value", headers=headers)
    assert r.status_code == 200

    r = client.get(f"/paper-trading/orders/{order_id}/journal", headers=headers)
    assert r.status_code == 200, r.text
    entry = r.json()
    entry_id = entry["id"]

    r = client.get(f"/paper-trading/accounts/{account_id}/journal", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.patch(f"/paper-trading/journal/{entry_id}/notes", json={"notes": "good trade"}, headers=headers)
    assert r.status_code == 200 and r.json()["notes"] == "good trade"

    r = client.post(f"/paper-trading/journal/{entry_id}/tags", json={"tags": ["btc", "swing"]}, headers=headers)
    assert r.status_code == 200 and set(r.json()["tags"]) == {"btc", "swing"}

    r = client.post(
        f"/paper-trading/journal/{entry_id}/screenshots", json={"url": "https://x/y.png", "caption": "entry"},
        headers=headers,
    )
    assert r.status_code == 200


def test_limit_order_modify_and_cancel(client, cleanup):
    headers = _register_and_login(client, "limit")
    account = client.post("/paper-trading/accounts", json={"starting_balance": 200000.0}, headers=headers).json()
    account_id = account["id"]

    r = client.post(
        f"/paper-trading/accounts/{account_id}/orders",
        json={"symbol": "ETH-USD", "side": "buy", "order_type": "limit", "quantity": 1.0, "limit_price": 100.0},
        headers=headers,
    )
    assert r.status_code == 200
    order = r.json()
    assert order["status"] == "pending"

    r = client.patch(f"/paper-trading/orders/{order['id']}", json={"limit_price": 90.0}, headers=headers)
    assert r.status_code == 200 and r.json()["limit_price"] == 90.0

    r = client.delete(f"/paper-trading/orders/{order['id']}", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"

    r = client.get(f"/paper-trading/accounts/{account_id}/orders", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.get(f"/paper-trading/accounts/{account_id}/orders?status=cancelled", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1


def test_analytics_reports_and_equity_curve(client, cleanup):
    headers = _register_and_login(client, "analytics")
    account = client.post("/paper-trading/accounts", json={"starting_balance": 200000.0}, headers=headers).json()
    account_id = account["id"]

    client.post(
        f"/paper-trading/accounts/{account_id}/orders",
        json={"symbol": "BTC-USD", "side": "buy", "order_type": "market", "quantity": 0.2}, headers=headers,
    )
    r = client.post(
        f"/paper-trading/accounts/{account_id}/orders",
        json={"symbol": "BTC-USD", "side": "sell", "order_type": "market", "quantity": 0.2}, headers=headers,
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/paper-trading/accounts/{account_id}/analytics", headers=headers)
    assert r.status_code == 200 and r.json()["total_trades"] == 1

    r = client.get(f"/paper-trading/accounts/{account_id}/trades", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.get(f"/paper-trading/accounts/{account_id}/equity-curve", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 2

    r = client.get(f"/paper-trading/accounts/{account_id}/monthly-performance", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    for period in ("daily", "weekly", "monthly", "yearly"):
        r = client.get(f"/paper-trading/accounts/{account_id}/reports/{period}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["period"] == period


def test_cross_user_access_is_denied(client, cleanup):
    headers = _register_and_login(client, "owner")
    other_headers = _register_and_login(client, "intruder")
    account = client.post("/paper-trading/accounts", json={"starting_balance": 10000.0}, headers=headers).json()

    r = client.get(f"/paper-trading/accounts/{account['id']}", headers=other_headers)
    assert r.status_code == 403

    r = client.post(
        f"/paper-trading/accounts/{account['id']}/orders",
        json={"symbol": "BTC-USD", "side": "buy", "order_type": "market", "quantity": 0.1},
        headers=other_headers,
    )
    assert r.status_code == 403
