"""
Unit tests for the two new shock-detection fields added to
MultiTimeframeAnalyzer._analyze_macro: daily_return_pct and
price_move_atr_multiple. Uses synthetic OHLC data (no network calls).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import numpy as np
import pandas as pd

from core.mtf_analyzer import MultiTimeframeAnalyzer


def _make_daily_df(n: int = 260, start: float = 100.0, last_move_pct: float = None, seed: int = 7) -> pd.DataFrame:
    """Synthetic daily OHLC: a small random walk, with the LAST day's move
    forced to an exact percentage (relative to the second-to-last close) so
    tests can assert exact/comparative values without network data."""
    rng = np.random.default_rng(seed)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + rng.normal(0, 0.003)))
    closes = np.array(closes)
    if last_move_pct is not None:
        closes[-1] = closes[-2] * (1 + last_move_pct / 100)
    highs = closes * 1.01
    lows = closes * 0.99
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"High": highs, "Low": lows, "Close": closes}, index=idx)


ANALYZER = MultiTimeframeAnalyzer()


class TestDailyReturnPct:
    def test_matches_exact_forced_move(self):
        df = _make_daily_df(last_move_pct=3.0)
        result = ANALYZER._analyze_macro(df)
        assert abs(result["daily_return_pct"] - 3.0) < 0.01

    def test_negative_move_is_negative(self):
        df = _make_daily_df(last_move_pct=-4.0)
        result = ANALYZER._analyze_macro(df)
        assert result["daily_return_pct"] < 0
        assert abs(result["daily_return_pct"] - (-4.0)) < 0.01


class TestPriceMoveAtrMultiple:
    def test_present_and_non_negative(self):
        df = _make_daily_df(last_move_pct=1.0)
        result = ANALYZER._analyze_macro(df)
        assert "price_move_atr_multiple" in result
        assert result["price_move_atr_multiple"] >= 0

    def test_larger_move_yields_larger_multiple(self):
        small = ANALYZER._analyze_macro(_make_daily_df(last_move_pct=0.1, seed=7))
        big = ANALYZER._analyze_macro(_make_daily_df(last_move_pct=10.0, seed=7))
        assert big["price_move_atr_multiple"] > small["price_move_atr_multiple"]


class TestExistingFieldsUnaffected:
    def test_all_original_keys_still_present(self):
        df = _make_daily_df()
        result = ANALYZER._analyze_macro(df)
        for key in ("trend_direction", "ema50", "ema200", "ema_bullish_crossover",
                    "supertrend_bullish", "weekly_trend_up", "atr_daily"):
            assert key in result
