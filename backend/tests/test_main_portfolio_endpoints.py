"""
Tests for the new /portfolios* endpoints - the Portfolio Intelligence
Platform's entry point into main.py. Real PostgreSQL/Redis/network,
matching this project's established testing philosophy. A structurally
distinct path (`/portfolios`, plural) from the legacy `/portfolio/optimize`
- both are asserted to keep working.
"""
from decision_engine.repository import PostgresExecutionRepository
from feature_store.config import FeatureStoreConfig
from learning.persistence import LearningRepository
from portfolio.repository import PortfolioRepository

_OWNER = "main-portfolio-test-owner"
_SYMBOL = "AAPL"


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
    repo = PortfolioRepository()
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM portfolio_snapshots WHERE portfolio_id IN "
                "(SELECT id FROM portfolio_portfolios WHERE owner = %s)", (_OWNER,),
            )
            cur.execute(
                "DELETE FROM portfolio_transactions WHERE portfolio_id IN "
                "(SELECT id FROM portfolio_portfolios WHERE owner = %s)", (_OWNER,),
            )
            cur.execute("DELETE FROM portfolio_portfolios WHERE owner = %s", (_OWNER,))
    finally:
        repo._pool.putconn(conn)


def _create_and_fund(client, deposit: float = 10000.0) -> int:
    response = client.post("/portfolios", json={"name": "Main Test", "owner": _OWNER})
    assert response.status_code == 200
    portfolio_id = response.json()["id"]
    response = client.post(f"/portfolios/{portfolio_id}/deposit", json={"amount": deposit})
    assert response.status_code == 200
    return portfolio_id


def test_legacy_portfolio_optimize_endpoint_is_unaffected(client):
    response = client.post("/portfolio/optimize", json={"symbols": [_SYMBOL, "MSFT"], "risk_tolerance": 0.5})
    assert response.status_code == 200
    body = response.json()
    assert "weights" in body
    assert "sharpe_ratio" in body


def test_create_deposit_buy_and_read_positions(client):
    portfolio_id = _create_and_fund(client)
    try:
        response = client.post(
            f"/portfolios/{portfolio_id}/buy", json={"symbol": _SYMBOL, "quantity": 5, "price": 150.0},
        )
        assert response.status_code == 200
        assert response.json()["transaction_type"] == "buy"

        response = client.get(f"/portfolios/{portfolio_id}/positions")
        assert response.status_code == 200
        positions = response.json()
        assert len(positions) == 1
        assert positions[0]["symbol"] == _SYMBOL
    finally:
        _cleanup()


def test_sell_more_than_held_returns_400(client):
    portfolio_id = _create_and_fund(client)
    try:
        client.post(f"/portfolios/{portfolio_id}/buy", json={"symbol": _SYMBOL, "quantity": 1, "price": 150.0})
        response = client.post(
            f"/portfolios/{portfolio_id}/sell", json={"symbol": _SYMBOL, "quantity": 1000, "price": 150.0},
        )
        assert response.status_code == 400
    finally:
        _cleanup()


def test_withdraw_more_than_cash_returns_400(client):
    portfolio_id = _create_and_fund(client, deposit=100.0)
    try:
        response = client.post(f"/portfolios/{portfolio_id}/withdraw", json={"amount": 999999.0})
        assert response.status_code == 400
    finally:
        _cleanup()


def test_unknown_portfolio_id_returns_404(client):
    response = client.get("/portfolios/999999999/positions")
    assert response.status_code == 404


def test_dashboard_endpoint_returns_full_shape(client):
    portfolio_id = _create_and_fund(client)
    try:
        client.post(f"/portfolios/{portfolio_id}/buy", json={"symbol": _SYMBOL, "quantity": 5, "price": 150.0})
        response = client.get(f"/portfolios/{portfolio_id}/dashboard")
        assert response.status_code == 200
        body = response.json()
        for field in ("portfolio_id", "cash_balance", "total_value", "positions", "allocation", "recommendations"):
            assert field in body
        assert body["portfolio_id"] == portfolio_id
    finally:
        _cleanup()


def test_history_and_snapshot_endpoints(client):
    portfolio_id = _create_and_fund(client)
    try:
        response = client.post(f"/portfolios/{portfolio_id}/snapshot")
        assert response.status_code == 200
        assert response.json()["portfolio_id"] == portfolio_id

        response = client.get(f"/portfolios/{portfolio_id}/history")
        assert response.status_code == 200
        assert len(response.json()) >= 1

        response = client.get(f"/portfolios/{portfolio_id}/history")  # deposit transaction, no symbol filter
        assert any(txn["transaction_type"] == "deposit" for txn in response.json())
    finally:
        _cleanup()


def test_list_portfolios_for_owner(client):
    portfolio_id = _create_and_fund(client)
    try:
        response = client.get("/portfolios", params={"owner": _OWNER})
        assert response.status_code == 200
        assert any(p["id"] == portfolio_id for p in response.json())
    finally:
        _cleanup()


def test_create_portfolio_without_owner_or_auth_returns_401(client):
    response = client.post("/portfolios", json={"name": "No Owner"})
    assert response.status_code == 401
