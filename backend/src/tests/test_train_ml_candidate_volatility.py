"""Unit test for train_ml_candidate_volatility.py's
_naive_trailing_volatility - the one genuinely new piece of logic in
this script (everything else reuses ml_training/CachingPriceFetcher
unchanged). The actual end-to-end training run against the real
(already-backfilled) Feature Store is exercised manually, matching
test_train_ml_candidate.py's own precedent for the base script."""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone

import pandas as pd

from learning.evaluator import OutcomeEvaluator
from scripts.train_ml_candidate_volatility import _naive_trailing_volatility


class _FakeCachingPriceFetcher:
    """Minimal stand-in for CachingPriceFetcher - same (symbol, start,
    end) -> Optional[DataFrame] contract, no real yfinance/network."""

    def __init__(self, history: pd.DataFrame | None) -> None:
        self._history = history

    def __call__(self, symbol, start, end):
        if self._history is None:
            return None
        sliced = self._history[(self._history.index >= start) & (self._history.index <= end)]
        return sliced if not sliced.empty else None


def _price_history(days: int = 30, start_price: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=days, freq="D", tz="UTC")
    # A simple, deterministic wiggle so realized volatility is nonzero.
    closes = [start_price * (1 + 0.01 * ((-1) ** i)) for i in range(days)]
    return pd.DataFrame({"Close": closes}, index=idx)


def test_matches_realized_volatility_over_the_trailing_window():
    history = _price_history(30)
    as_of = datetime(2026, 1, 20, tzinfo=timezone.utc)
    fetcher = _FakeCachingPriceFetcher(history)

    result = _naive_trailing_volatility(fetcher, "AAPL", as_of, horizon_days=5)

    expected = OutcomeEvaluator._realized_volatility(history, as_of - timedelta(days=5), as_of)
    assert result == expected
    assert result is not None and result > 0


def test_returns_none_when_no_price_history_is_available():
    fetcher = _FakeCachingPriceFetcher(None)
    as_of = datetime(2026, 1, 20, tzinfo=timezone.utc)
    assert _naive_trailing_volatility(fetcher, "AAPL", as_of, horizon_days=5) is None


def test_returns_none_when_the_trailing_window_has_no_overlapping_data():
    history = _price_history(5, start_price=100.0)  # only covers 2026-01-01..01-05
    as_of = datetime(2026, 6, 1, tzinfo=timezone.utc)  # far outside that range
    fetcher = _FakeCachingPriceFetcher(history)
    assert _naive_trailing_volatility(fetcher, "AAPL", as_of, horizon_days=5) is None
