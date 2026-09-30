"""
Tests for the new /portfolios* endpoints - the Portfolio Intelligence
Platform's entry point into main.py. Real PostgreSQL/Redis/network,
matching this project's established testing philosophy. A structurally
distinct path (`/portfolios`, plural) from the legacy `/portfolio/optimize`
- both are asserted to keep working.

These endpoints require a real Users-platform JWT (see `_get_current_user`
in main.py) - the portfolio `owner` is always the authenticated caller's
email, never a caller-supplied value, closing the IDOR/owner-spoofing hole
described in the production audit ("Auth can silently disable itself, and
identity is inconsistently checked").
"""
from decision_engine.repository import PostgresExecutionRepository
from feature_store.config import FeatureStoreConfig
from learning.persistence import LearningRepository
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService
from users.repository import UsersRepository

_EMAIL_PREFIX = "main-portfolio-test"
_SYMBOL = "AAPL"


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register_and_login(client, name):
    client.post("/auth/register", json={"email": _email(name), "password": "MyPassw0rd1", "display_name": name})
    r = client.post("/auth/login", json={"email": _email(name), "password": "MyPassw0rd1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _cleanup_pipeline_side_effects() -> None:
    """The dashboard/recommendations endpoints wire the real
    `pipeline.service.PipelineService` into `RecommendationEngine` for
    Decision Engine signal recommendations (requirement 7) - a real
    held position triggers a real Pipeline run, which persists a real
    `decision_engine_executions` row and a real Continuous Learning
    `learning_samples` row, exactly like `/quant/analyze` already does
    (see test_main_quant_endpoint.py's own identical cleanup)."""
    exec_repo = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    conn = exec_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM decision_engine_executions WHERE symbol = %s AND aggregation_strategy_version = %s",
                (_SYMBOL, "pipeline_parallel_v1"),
            )
    finally:
        exec_repo._pool.putconn(conn)
    exec_repo.close()

    learning_repo = LearningRepository()
    conn2 = learning_repo._pool.getconn()
    try:
        with conn2, conn2.cursor() as cur:
            cur.execute(
                "DELETE FROM learning_samples WHERE symbol = %s AND decided_at > now() - interval '10 minutes'",
                (_SYMBOL,),
            )
    finally:
        learning_repo._pool.putconn(conn2)


def _cleanup() -> None:
    _cleanup_pipeline_side_effects()
    port_repo = PortfolioRepository()
    conn = port_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM portfolio_portfolios WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",),
            )
            portfolio_ids = [r[0] for r in cur.fetchall()]
            if portfolio_ids:
                cur.execute("DELETE FROM portfolio_snapshots WHERE portfolio_id = ANY(%s)", (portfolio_ids,))
                cur.execute("DELETE FROM portfolio_transactions WHERE portfolio_id = ANY(%s)", (portfolio_ids,))
                cur.execute("DELETE FROM portfolio_portfolios WHERE id = ANY(%s)", (portfolio_ids,))
    finally:
        port_repo._pool.putconn(conn)

    users_repo = UsersRepository()
    conn3 = users_repo._connection()
    with conn3 as conn3_ctx, conn3_ctx, conn3_ctx.cursor() as cur:
        cur.execute("SELECT id FROM users_users WHERE email LIKE %s", (f"{_EMAIL_PREFIX}%",))
        user_ids = [r[0] for r in cur.fetchall()]
        if user_ids:
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (user_ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (user_ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (user_ids,))


def _create_and_fund(owner_email: str, deposit: float = 10000.0) -> int:
    """Seeds a funded portfolio directly through the service layer,
    bypassing the rate-limited `POST /portfolios` HTTP endpoint - most
    tests below only need a portfolio to exist, they aren't exercising
    creation itself (that's covered separately by
    `test_create_portfolio_ignores_caller_supplied_owner` and
    `test_create_portfolio_without_auth_returns_401`)."""
    service = PortfolioService()
    portfolio = service.create_portfolio(owner=owner_email, name="Main Test")
    if deposit:
        service.deposit(portfolio.id, deposit)
    return portfolio.id


def test_legacy_portfolio_optimize_endpoint_is_unaffected(client):
    response = client.post("/portfolio/optimize", json={"symbols": [_SYMBOL, "MSFT"], "risk_tolerance": 0.5})
    assert response.status_code == 200
    body = response.json()
    assert "weights" in body
    assert "sharpe_ratio" in body


def test_create_deposit_buy_and_read_positions(client):
    headers = _register_and_login(client, "owner1")
    try:
        portfolio_id = _create_and_fund(_email("owner1"))
        response = client.post(
            f"/portfolios/{portfolio_id}/buy", json={"symbol": _SYMBOL, "quantity": 5, "price": 150.0},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["transaction_type"] == "buy"

        response = client.get(f"/portfolios/{portfolio_id}/positions", headers=headers)
        assert response.status_code == 200
        positions = response.json()
        assert len(positions) == 1
        assert positions[0]["symbol"] == _SYMBOL
    finally:
        _cleanup()


def test_sell_more_than_held_returns_400(client):
    headers = _register_and_login(client, "oversell")
    try:
        portfolio_id = _create_and_fund(_email("oversell"))
        client.post(
            f"/portfolios/{portfolio_id}/buy", json={"symbol": _SYMBOL, "quantity": 1, "price": 150.0},
            headers=headers,
        )
        response = client.post(
            f"/portfolios/{portfolio_id}/sell", json={"symbol": _SYMBOL, "quantity": 1000, "price": 150.0},
            headers=headers,
        )
        assert response.status_code == 400
    finally:
        _cleanup()


def test_withdraw_more_than_cash_returns_400(client):
    headers = _register_and_login(client, "overdraw")
    try:
        portfolio_id = _create_and_fund(_email("overdraw"), deposit=100.0)
        response = client.post(
            f"/portfolios/{portfolio_id}/withdraw", json={"amount": 999999.0}, headers=headers,
        )
        assert response.status_code == 400
    finally:
        _cleanup()


def test_unknown_portfolio_id_returns_404(client):
    headers = _register_and_login(client, "unknown-id")
    try:
        response = client.get("/portfolios/999999999/positions", headers=headers)
        assert response.status_code == 404
    finally:
        _cleanup()


def test_dashboard_endpoint_returns_full_shape(client):
    headers = _register_and_login(client, "dashboard")
    try:
        portfolio_id = _create_and_fund(_email("dashboard"))
        client.post(
            f"/portfolios/{portfolio_id}/buy", json={"symbol": _SYMBOL, "quantity": 5, "price": 150.0},
            headers=headers,
        )
        response = client.get(f"/portfolios/{portfolio_id}/dashboard", headers=headers)
        assert response.status_code == 200
        body = response.json()
        for field in ("portfolio_id", "cash_balance", "total_value", "positions", "allocation", "recommendations"):
            assert field in body
        assert body["portfolio_id"] == portfolio_id
    finally:
        _cleanup()


def test_history_and_snapshot_endpoints(client):
    headers = _register_and_login(client, "history")
    try:
        portfolio_id = _create_and_fund(_email("history"))
        response = client.post(f"/portfolios/{portfolio_id}/snapshot", headers=headers)
        assert response.status_code == 200
        assert response.json()["portfolio_id"] == portfolio_id

        response = client.get(f"/portfolios/{portfolio_id}/history", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) >= 1

        response = client.get(f"/portfolios/{portfolio_id}/history", headers=headers)  # deposit txn, no symbol filter
        assert any(txn["transaction_type"] == "deposit" for txn in response.json())
    finally:
        _cleanup()


def test_list_portfolios_returns_only_the_callers_own(client):
    headers = _register_and_login(client, "list-mine")
    other_headers = _register_and_login(client, "list-other")
    try:
        portfolio_id = _create_and_fund(_email("list-mine"))
        _create_and_fund(_email("list-other"))

        response = client.get("/portfolios", headers=headers)
        assert response.status_code == 200
        ids = [p["id"] for p in response.json()]
        assert portfolio_id in ids
        assert all(p["owner"] == _email("list-mine") for p in response.json())
    finally:
        _cleanup()


def test_create_portfolio_without_auth_returns_401(client):
    response = client.post("/portfolios", json={"name": "No Auth"})
    assert response.status_code == 401


# ── IDOR / owner-spoofing regression (production audit: "Auth can
# silently disable itself, and identity is inconsistently checked") ──────
#
# Before the fix, `verify_firebase_token` returned `uid=None` whenever
# Firebase wasn't configured (the actual state of this deployment - no
# firebase-credentials.json anywhere in the repo), which let
# `_resolve_portfolio_owner` accept any caller-supplied `owner` string
# and let `_authorize_portfolio_access` skip its ownership check
# entirely - full IDOR on every `/portfolios/{id}/...` endpoint. These
# tests prove neither hole exists anymore.

def test_create_portfolio_ignores_caller_supplied_owner(client):
    headers = _register_and_login(client, "spoof-create")
    try:
        response = client.post(
            "/portfolios", json={"name": "Spoofed", "owner": "someone-else@example.com"}, headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["owner"] == _email("spoof-create")
    finally:
        _cleanup()


def test_cannot_read_another_owners_portfolio(client):
    owner_headers = _register_and_login(client, "idor-owner")
    intruder_headers = _register_and_login(client, "idor-intruder")
    try:
        portfolio_id = _create_and_fund(_email("idor-owner"))
        response = client.get(f"/portfolios/{portfolio_id}/positions", headers=intruder_headers)
        assert response.status_code == 403
    finally:
        _cleanup()


def test_cannot_withdraw_from_another_owners_portfolio(client):
    owner_headers = _register_and_login(client, "idor-withdraw-owner")
    intruder_headers = _register_and_login(client, "idor-withdraw-intruder")
    try:
        portfolio_id = _create_and_fund(_email("idor-withdraw-owner"), deposit=1000.0)
        response = client.post(
            f"/portfolios/{portfolio_id}/withdraw", json={"amount": 500.0}, headers=intruder_headers,
        )
        assert response.status_code == 403
        # the real owner's cash must be completely untouched by the attempt
        response = client.get(f"/portfolios/{portfolio_id}/history", headers=owner_headers)
        assert response.status_code == 200
        assert not any(txn["transaction_type"] == "withdrawal" for txn in response.json())
    finally:
        _cleanup()


def test_all_portfolio_endpoints_require_authentication(client):
    portfolio_id = _create_and_fund(_email("noauth-setup"))
    try:
        assert client.get("/portfolios").status_code == 401
        assert client.post(f"/portfolios/{portfolio_id}/deposit", json={"amount": 1.0}).status_code == 401
        assert client.post(f"/portfolios/{portfolio_id}/withdraw", json={"amount": 1.0}).status_code == 401
        assert client.post(
            f"/portfolios/{portfolio_id}/buy", json={"symbol": _SYMBOL, "quantity": 1, "price": 1.0},
        ).status_code == 401
        assert client.post(
            f"/portfolios/{portfolio_id}/sell", json={"symbol": _SYMBOL, "quantity": 1, "price": 1.0},
        ).status_code == 401
        assert client.get(f"/portfolios/{portfolio_id}/positions").status_code == 401
        assert client.get(f"/portfolios/{portfolio_id}/history").status_code == 401
        assert client.post(f"/portfolios/{portfolio_id}/snapshot").status_code == 401
    finally:
        _cleanup()
