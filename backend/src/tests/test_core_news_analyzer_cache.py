"""
Regression tests for core/news_analyzer.py's caching (production audit
MEDIUM #4: `_NEWS_CACHE` duplicated the module-level dict+timestamp
pattern `core/cache_manager.TTLCache` already exists to replace).
`_fetch_yfinance_news` is monkeypatched to a deterministic fake so
these are fast and don't depend on real network/market data - the
canonical TTLCache mechanics themselves (expiry boundary, thread
safety, ...) are already exhaustively covered by
tests/test_cache_manager.py; these tests only prove analyze_news
correctly delegates to it.
"""
from datetime import datetime, timezone

import pytest

from core.cache_manager import TTLCache
from core.news_analyzer import _NEWS_CACHE, analyze_news


def test_news_cache_is_a_real_ttlcache_instance():
    # Structural guard for the actual MEDIUM #4 change: _NEWS_CACHE must
    # be the shared TTLCache infrastructure, not a second bespoke
    # dict+timestamp cache.
    assert isinstance(_NEWS_CACHE, TTLCache)


@pytest.fixture(autouse=True)
def clear_news_cache():
    _NEWS_CACHE.clear()
    yield
    _NEWS_CACHE.clear()


def _fake_news(title="Positive earnings beat", n=1):
    now = datetime.now(timezone.utc)
    return [
        {"title": f"{title} {i}", "summary": "Strong quarter, raised guidance.", "published_at": now, "source": "Test Wire"}
        for i in range(n)
    ]


def test_cache_hit_avoids_a_second_fetch(monkeypatch):
    calls = []

    def _fetch(symbol, max_news=15):
        calls.append(symbol)
        return _fake_news()

    monkeypatch.setattr("core.news_analyzer._fetch_yfinance_news", _fetch)

    first = analyze_news("AAPL", market="US", use_cache=True)
    second = analyze_news("AAPL", market="US", use_cache=True)

    assert calls == ["AAPL"]  # only fetched once - second call was a cache hit
    assert second is first  # TTLCache stores by reference (see test_cache_manager.py)


def test_use_cache_false_always_recomputes_but_still_populates_the_cache(monkeypatch):
    calls = []
    monkeypatch.setattr("core.news_analyzer._fetch_yfinance_news", lambda symbol, max_news=15: calls.append(symbol) or _fake_news())

    analyze_news("AAPL", market="US", use_cache=False)
    analyze_news("AAPL", market="US", use_cache=False)
    assert calls == ["AAPL", "AAPL"]  # use_cache=False bypasses reading the cache...

    # ...but every call still writes the cache, so a later use_cache=True
    # call is a hit without any extra fetch.
    third = analyze_news("AAPL", market="US", use_cache=True)
    assert calls == ["AAPL", "AAPL"]
    assert third is not None


def test_cache_expiry_triggers_a_recompute(monkeypatch):
    calls = []
    monkeypatch.setattr("core.news_analyzer._fetch_yfinance_news", lambda symbol, max_news=15: calls.append(symbol) or _fake_news())

    fake_now = [1_000_000.0]
    monkeypatch.setattr("core.cache_manager.time.time", lambda: fake_now[0])

    analyze_news("AAPL", market="US", use_cache=True)
    assert calls == ["AAPL"]

    fake_now[0] += 1800.0  # exactly the 30-minute TTL - already expired (inclusive >=, see TTLCache)
    analyze_news("AAPL", market="US", use_cache=True)
    assert calls == ["AAPL", "AAPL"]


def test_different_symbols_and_markets_are_independent_cache_keys(monkeypatch):
    calls = []
    monkeypatch.setattr("core.news_analyzer._fetch_yfinance_news", lambda symbol, max_news=15: calls.append(symbol) or _fake_news())

    analyze_news("AAPL", market="US", use_cache=True)
    analyze_news("MSFT", market="US", use_cache=True)
    analyze_news("AAPL", market="US", use_cache=True)  # cache hit, no new call
    analyze_news("AAPL", market="TR", use_cache=True)  # same symbol, different market -> distinct key

    assert calls == ["AAPL", "MSFT", "AAPL"]


def test_no_news_result_is_also_cached(monkeypatch):
    calls = []
    monkeypatch.setattr("core.news_analyzer._fetch_yfinance_news", lambda symbol, max_news=15: calls.append(symbol) or [])

    first = analyze_news("ZZZZ", market="US", use_cache=True)
    second = analyze_news("ZZZZ", market="US", use_cache=True)

    assert first.total_news == 0
    assert calls == ["ZZZZ"]  # the "no news" early-return result was cached too
    assert second is first
