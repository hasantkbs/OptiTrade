"""Integration tests for GET /market/snapshot and the zero-behavior-
change extraction of _build_chart_response from GET /chart/{symbol}.
Uses the shared `client` fixture (real main.app - see conftest.py).
No auth required on either endpoint, matching GET /chart/{symbol}'s
existing convention."""
from unittest.mock import patch


def test_chart_endpoint_unchanged_after_extraction(client):
    """The single most important test in this task: GET /chart/{symbol}
    must behave byte-for-byte identically to before the
    _build_chart_response extraction."""
    r = client.get("/chart/AAPL?period=1mo")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["period"] == "1mo"
    assert isinstance(body["points"], list)
    assert len(body["points"]) > 0
    assert "close" in body["points"][0]
    assert "volume" in body["points"][0]


def test_chart_endpoint_still_404s_for_unknown_symbol(client):
    r = client.get("/chart/NOT-A-REAL-SYMBOL-XYZ?period=1mo")
    assert r.status_code == 404


def test_market_snapshot_returns_both_indices_and_dominance(client):
    with patch("main.get_btc_dominance", return_value=54.3):
        r = client.get("/market/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["bist100"] is not None
    assert body["btc"] is not None
    assert body["btc_dominance_pct"] == 54.3
    assert "generated_at" in body


def test_market_snapshot_degrades_to_null_dominance_on_coingecko_failure(client):
    """GET /market/snapshot when CoinGecko fails but BIST100/BTC
    succeed must return 200 with btc_dominance_pct: null, never a 500."""
    with patch("main.get_btc_dominance", return_value=None):
        r = client.get("/market/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["btc_dominance_pct"] is None
    assert body["bist100"] is not None
    assert body["btc"] is not None


def test_market_snapshot_degrades_to_null_bist100_when_that_fetch_fails(client):
    """Symmetric case: if one index chart's own fetch_history call
    fails while the other index and CoinGecko both succeed, the
    response must still be 200 with that one field null, never a 500."""
    with patch("main._build_chart_response", side_effect=[None, {"symbol": "BTC-USD", "period": "3mo", "points": [], "change_pct": 0.0, "high": 0.0, "low": 0.0}]), \
         patch("main.get_btc_dominance", return_value=54.3):
        r = client.get("/market/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["bist100"] is None
    assert body["btc"] is not None
