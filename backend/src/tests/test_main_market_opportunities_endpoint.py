"""Tests for GET /market/opportunities/{market} - reads market_
opportunities_refresh_loop's cache only; never falls back to a live
scan (that would take far longer than any request should wait - see
the endpoint's own docstring in main.py)."""
import pytest

import main as main_module
from intelligence.models import (
    OpportunityAssessment,
    OpportunityLabel,
    OpportunityRankingResult,
    RankedOpportunity,
    RankingReason,
    RiskBucket,
)
from pipeline.models import PipelineMetadata, PipelineResponse, RiskAssessment
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


def _fake_ranked_opportunity(rank: int, symbol: str) -> RankedOpportunity:
    response = PipelineResponse(
        symbol=symbol, decision="BUY", confidence=0.7, expected_return=0.02, expected_volatility=0.1,
        risk=RiskAssessment(risk_level="LOW", expected_volatility=0.1, data_sufficiency=0.9),
        explanation="test",
        metadata=PipelineMetadata(
            pipeline_version="1.0.0", total_duration_ms=1.0,
            engines_available=3, engines_succeeded=3, degraded=False,
        ),
    )
    assessment = OpportunityAssessment(
        symbol=symbol, decision="BUY", confidence=0.7, expected_return=0.02,
        expected_volatility=0.1, risk_bucket=RiskBucket.LOW, data_sufficiency=0.9,
        classification=OpportunityLabel.BUY_BIAS, timestamp="2026-01-01T00:00:00Z",
    )
    return RankedOpportunity(
        rank=rank, symbol=symbol, assessment=assessment, response=response,
        reason=RankingReason(label_priority=0, risk_rank=0),
    )


def test_refresh_caps_the_cached_ranking_at_ten_results(monkeypatch):
    """_refresh_market_opportunities must cap what it caches at 10 -
    "en fazla 10 opsiyonu sıralasın" (rank at most 10 options), the
    Market page's own top-opportunities picker. rank_opportunities
    itself ranks every successfully-scanned symbol with no limit of
    its own (see intelligence/opportunity_ranking.py) - the cap is this
    function's own responsibility, not something to re-derive
    elsewhere."""
    twelve_ranked = [_fake_ranked_opportunity(i, f"SYM{i}") for i in range(1, 13)]

    def _fake_scan_and_rank(scanner, symbols, config=None):
        return OpportunityRankingResult(
            ranked=twelve_ranked, failed_symbols=[], unclassifiable_symbols=[],
            ranked_count=len(twelve_ranked), total_scanned_count=len(twelve_ranked),
        )

    monkeypatch.setattr(main_module, "scan_and_rank", _fake_scan_and_rank)

    cached: dict = {}

    class _RecordingCache:
        def set(self, market, payload, ttl_seconds=None):
            cached[market] = payload

    monkeypatch.setattr(main_module, "_opportunities_cache", _RecordingCache())
    monkeypatch.setattr(main_module, "_pipeline_service", object())

    main_module._refresh_market_opportunities("US")

    stored = main_module.MarketOpportunitiesResponse.model_validate_json(cached["US"])
    assert len(stored.opportunities) == 10
    assert [item.symbol for item in stored.opportunities] == [f"SYM{i}" for i in range(1, 11)]


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


def test_refresh_market_opportunities_uses_higher_concurrency_for_us(monkeypatch):
    """US's symbol universe is now the full S&P 500 (~500 symbols) -
    the scanner's default concurrency (max_parallel_symbols=3) would
    make a single scan take far too long. US must get its own,
    higher-concurrency MarketScannerConfig; TR/CRYPTO keep the default."""
    import intelligence.market_scanner as market_scanner_module

    captured_configs = []
    original_init = market_scanner_module.MarketScanner.__init__

    def _capturing_init(self, pipeline_service=None, config=None):
        captured_configs.append(config)
        original_init(self, pipeline_service=pipeline_service, config=config)

    monkeypatch.setattr(market_scanner_module.MarketScanner, "__init__", _capturing_init)
    monkeypatch.setattr(main_module, "scan_and_rank", lambda scanner, symbols, config=None: OpportunityRankingResult(
        ranked=[], failed_symbols=[], unclassifiable_symbols=[], ranked_count=0, total_scanned_count=0,
    ))
    monkeypatch.setattr(main_module, "_opportunities_cache", type("C", (), {"set": staticmethod(lambda m, p, ttl_seconds=None: None)})())
    monkeypatch.setattr(main_module, "_pipeline_service", object())

    main_module._refresh_market_opportunities("US")
    main_module._refresh_market_opportunities("TR")

    assert captured_configs[0] is not None and captured_configs[0].max_parallel_symbols == 5
    assert captured_configs[1] is None


def test_refresh_market_opportunities_gives_us_a_ttl_that_survives_its_own_cadence(monkeypatch):
    """US now refreshes at most every 6th tick (30 minutes, main.py's
    _MARKET_OPPORTUNITIES_US_TICK_INTERVAL *
    _MARKET_OPPORTUNITIES_REFRESH_INTERVAL_SECONDS) plus real scan
    time - the cache's 900s (15-minute) default TTL would expire the
    US entry before its own next refresh, making GET /market/
    opportunities/US return 503 most of the time. TR/CRYPTO still
    refresh every tick (300s) and must keep the default TTL."""
    monkeypatch.setattr(main_module, "scan_and_rank", lambda scanner, symbols, config=None: OpportunityRankingResult(
        ranked=[], failed_symbols=[], unclassifiable_symbols=[], ranked_count=0, total_scanned_count=0,
    ))
    captured_calls = []

    class _RecordingCache:
        def set(self, market, payload, ttl_seconds=None):
            captured_calls.append((market, ttl_seconds))

    monkeypatch.setattr(main_module, "_opportunities_cache", _RecordingCache())
    monkeypatch.setattr(main_module, "_pipeline_service", object())

    main_module._refresh_market_opportunities("US")
    main_module._refresh_market_opportunities("TR")

    us_ttl = dict(captured_calls)["US"]
    tr_ttl = dict(captured_calls)["TR"]
    min_us_survival = main_module._MARKET_OPPORTUNITIES_REFRESH_INTERVAL_SECONDS * main_module._MARKET_OPPORTUNITIES_US_TICK_INTERVAL
    assert us_ttl is not None and us_ttl > min_us_survival
    assert tr_ttl is None  # unchanged - still uses the cache's own configured default
