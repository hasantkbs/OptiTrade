"""Unit test for train_ml_candidate.py's CachingPriceFetcher - the
actual end-to-end training run against the real (now-backfilled)
Feature Store is exercised manually (this task's Step 3-5 below), not
here, matching this plan's Task 2 precedent."""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone

import pandas as pd

from scripts.train_ml_candidate import CachingPriceFetcher


def test_caching_price_fetcher_slices_without_refetching(monkeypatch):
    call_count = {"n": 0}

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end):
            call_count["n"] += 1
            idx = pd.date_range("2026-01-01", periods=10, freq="D", tz="UTC")
            return pd.DataFrame({"Close": range(10)}, index=idx)

    import scripts.train_ml_candidate as mod
    monkeypatch.setattr(mod.yf, "Ticker", _FakeTicker)

    fetcher = CachingPriceFetcher(["AAPL"], datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 10, tzinfo=timezone.utc))
    assert call_count["n"] == 1  # fetched once at construction, for the one symbol

    first = fetcher("AAPL", datetime(2026, 1, 2, tzinfo=timezone.utc), datetime(2026, 1, 5, tzinfo=timezone.utc))
    second = fetcher("AAPL", datetime(2026, 1, 3, tzinfo=timezone.utc), datetime(2026, 1, 6, tzinfo=timezone.utc))
    assert call_count["n"] == 1  # neither per-call slice triggered a new fetch
    assert first is not None and not first.empty
    assert second is not None and not second.empty


def test_caching_price_fetcher_returns_none_for_unknown_symbol():
    fetcher = CachingPriceFetcher([], datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 10, tzinfo=timezone.utc))
    assert fetcher("NOPE", datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc)) is None
