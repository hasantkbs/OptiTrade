"""Tests for core/sector_intelligence.py's get_sector_overview() running
sectors in parallel (performance fix: /dashboard/market scanned every
sector serially, each already parallel internally, so total latency
scaled with sector count on top of each sector's own network-bound
cost). `analyze_sector` is monkeypatched to a fast deterministic fake so
these are quick and prove the orchestration, not sector/network
internals - those are already covered by
test_core_sector_intelligence_cache.py and the sector-level tests."""
import time

import pytest

from core.sector_intelligence import SECTOR_DEFINITIONS, SectorResult, get_sector_overview


def _fake_result(sector_key: str, market: str, opportunity_score: float) -> SectorResult:
    defn = SECTOR_DEFINITIONS[sector_key]
    return SectorResult(
        sector=sector_key, name_tr=defn["name_tr"], icon=defn.get("icon", "📊"),
        description=defn.get("description", ""), market=market,
        opportunity_score=opportunity_score, trend="NEUTRAL", opportunity_label="NÖTR / İZLE",
        avg_technical=50, avg_news_delta=0, avg_change_pct=0, bullish_count=0, total_count=1,
        top_symbols=[], symbols=[], advice="", risk=defn.get("risk", "MEDIUM"),
    )


def test_runs_every_active_sector_and_sorts_by_opportunity_score(monkeypatch):
    calls = []

    def _fake_analyze_sector(sector_key, market="US", max_workers=6, use_cache=True):
        calls.append(sector_key)
        scores = {"TECH": 90.0, "ENERGY": 40.0, "FINANCE": 70.0}
        return _fake_result(sector_key, market, scores.get(sector_key, 50.0))

    monkeypatch.setattr("core.sector_intelligence.analyze_sector", _fake_analyze_sector)

    results = get_sector_overview(market="US")

    active_sectors = [k for k, v in SECTOR_DEFINITIONS.items() if v.get("us_symbols")]
    assert set(calls) == set(active_sectors)
    assert [r.opportunity_score for r in results] == sorted(
        (r.opportunity_score for r in results), reverse=True
    )


def test_one_sector_failure_does_not_drop_the_others(monkeypatch):
    def _fake_analyze_sector(sector_key, market="US", max_workers=6, use_cache=True):
        if sector_key == "ENERGY":
            raise RuntimeError("yfinance unreachable for this sector")
        return _fake_result(sector_key, market, 60.0)

    monkeypatch.setattr("core.sector_intelligence.analyze_sector", _fake_analyze_sector)

    results = get_sector_overview(market="US")

    active_sectors = [k for k, v in SECTOR_DEFINITIONS.items() if v.get("us_symbols")]
    assert "ENERGY" not in [r.sector for r in results]
    assert len(results) == len(active_sectors) - 1


def test_sectors_are_scanned_concurrently_not_serially(monkeypatch):
    # Each fake sector call blocks for a fixed slice; if get_sector_overview
    # still ran sectors one at a time this would take len(active_sectors)
    # times as long as running them together.
    active_sectors = [k for k, v in SECTOR_DEFINITIONS.items() if v.get("us_symbols")]
    assert len(active_sectors) >= 2, "test needs at least 2 active sectors to prove concurrency"

    def _slow_fake_analyze_sector(sector_key, market="US", max_workers=6, use_cache=True):
        time.sleep(0.2)
        return _fake_result(sector_key, market, 50.0)

    monkeypatch.setattr("core.sector_intelligence.analyze_sector", _slow_fake_analyze_sector)

    started = time.monotonic()
    get_sector_overview(market="US")
    elapsed = time.monotonic() - started

    assert elapsed < 0.2 * len(active_sectors), (
        f"took {elapsed:.2f}s for {len(active_sectors)} sectors at 0.2s each - looks serial"
    )
