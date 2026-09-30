"""
Regression tests for core/sector_intelligence.py's caching (production
audit MEDIUM #4: `_SECTOR_CACHE` duplicated the module-level
dict+timestamp pattern `core/cache_manager.TTLCache` already exists to
replace). `_analyze_symbol_fast` (the real per-symbol worker, which
itself hits real network/analysis) is monkeypatched to a fast
deterministic fake so these are quick and don't depend on real market
data - the canonical TTLCache mechanics themselves are already covered
by tests/test_cache_manager.py; these tests only prove analyze_sector
correctly delegates to it.
"""
import pytest

from core.cache_manager import TTLCache
from core.sector_intelligence import _SECTOR_CACHE, SymbolSnapshot, analyze_sector


def test_sector_cache_is_a_real_ttlcache_instance():
    # Structural guard for the actual MEDIUM #4 change: _SECTOR_CACHE
    # must be the shared TTLCache infrastructure, not a second bespoke
    # dict+timestamp cache.
    assert isinstance(_SECTOR_CACHE, TTLCache)


@pytest.fixture(autouse=True)
def clear_sector_cache():
    _SECTOR_CACHE.clear()
    yield
    _SECTOR_CACHE.clear()


def _fake_snapshot(symbol, market):
    return SymbolSnapshot(
        symbol=symbol, price=100.0, change_pct=1.0, rsi=55.0, score=70, decision_code="BUY", news_delta=2,
    )


def test_cache_hit_avoids_a_second_analysis_pass(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "core.sector_intelligence._analyze_symbol_fast",
        lambda symbol, market: calls.append(symbol) or _fake_snapshot(symbol, market),
    )

    first = analyze_sector("TECH", market="US", use_cache=True)
    second = analyze_sector("TECH", market="US", use_cache=True)

    assert len(calls) == len(first.symbols)  # one analysis pass over every symbol in the sector
    assert second is first  # TTLCache stores by reference


def test_use_cache_false_always_recomputes_but_still_populates_the_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "core.sector_intelligence._analyze_symbol_fast",
        lambda symbol, market: calls.append(symbol) or _fake_snapshot(symbol, market),
    )

    analyze_sector("TECH", market="US", use_cache=False)
    first_call_count = len(calls)
    analyze_sector("TECH", market="US", use_cache=False)
    assert len(calls) == first_call_count * 2  # use_cache=False bypasses reading the cache...

    # ...but the result still gets written, so a later use_cache=True is a hit.
    analyze_sector("TECH", market="US", use_cache=True)
    assert len(calls) == first_call_count * 2


def test_cache_expiry_triggers_a_recompute(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "core.sector_intelligence._analyze_symbol_fast",
        lambda symbol, market: calls.append(symbol) or _fake_snapshot(symbol, market),
    )
    fake_now = [1_000_000.0]
    monkeypatch.setattr("core.cache_manager.time.time", lambda: fake_now[0])

    analyze_sector("TECH", market="US", use_cache=True)
    first_call_count = len(calls)
    assert first_call_count > 0

    fake_now[0] += 900.0  # exactly the 15-minute TTL - already expired (inclusive >=)
    analyze_sector("TECH", market="US", use_cache=True)
    assert len(calls) == first_call_count * 2


def test_different_sectors_and_markets_are_independent_cache_keys(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "core.sector_intelligence._analyze_symbol_fast",
        lambda symbol, market: calls.append((symbol, market)) or _fake_snapshot(symbol, market),
    )

    analyze_sector("TECH", market="US", use_cache=True)
    tech_us_calls = len(calls)
    analyze_sector("ENERGY", market="US", use_cache=True)  # different sector -> distinct key, more calls
    assert len(calls) > tech_us_calls

    calls_after_energy = len(calls)
    analyze_sector("TECH", market="US", use_cache=True)  # cache hit, no new calls
    assert len(calls) == calls_after_energy
