"""
Backward-compatibility tests for main.py: every endpoint that existed
before the Quant Research Platform pipeline was wired in must continue
to work exactly as before. Real PostgreSQL/Redis/network - no mocks,
matching this project's established testing philosophy.
"""
EXPECTED_ROUTE_COUNT = 34  # 33 pre-existing routes + the new /quant/analyze


def test_route_count_is_the_expected_33_plus_the_new_quant_route(client):
    from main import app
    assert len(app.routes) == EXPECTED_ROUTE_COUNT


def test_openapi_generation_still_works_and_includes_legacy_and_new_paths(client):
    from main import app
    schema = app.openapi()
    assert "/analyze" in schema["paths"]
    assert "/quant/analyze" in schema["paths"]
    assert "/health" in schema["paths"]


def test_root_endpoint_unchanged(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_health_endpoint_unchanged(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_symbols_bist_endpoint_unchanged(client):
    response = client.get("/symbols/bist")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert "THYAO.IS" in body


def test_symbols_crypto_endpoint_unchanged(client):
    response = client.get("/symbols/crypto")
    assert response.status_code == 200
    body = response.json()
    assert "BTC-USD" in body


def test_market_list_endpoint_unchanged(client):
    response = client.get("/market/list")
    assert response.status_code == 200
    assert "markets" in response.json()


def test_sectors_list_endpoint_unchanged(client):
    response = client.get("/sectors/list/all")
    assert response.status_code == 200
    assert "sectors" in response.json()


def test_session_all_endpoint_unchanged(client):
    response = client.get("/session/all")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_ml_status_endpoint_unchanged(client):
    response = client.get("/ml/status")
    assert response.status_code == 200


def test_legacy_analyze_endpoint_still_returns_the_original_analysisresult_shape(client):
    response = client.post("/analyze", json={"symbol": "AAPL", "asset_type": "stock"})
    assert response.status_code == 200
    body = response.json()
    # These are exactly the AnalysisResult fields from models/schemas.py -
    # untouched by the new pipeline.
    for field in ("symbol", "decision", "decision_code", "score", "risk_level", "indicators", "asset_type"):
        assert field in body
    assert body["symbol"] == "AAPL"


def test_legacy_analyze_endpoint_404_for_unknown_symbol_unchanged(client):
    response = client.post("/analyze", json={"symbol": "THIS-IS-NOT-A-REAL-SYMBOL-XYZ", "asset_type": "stock"})
    assert response.status_code == 404
