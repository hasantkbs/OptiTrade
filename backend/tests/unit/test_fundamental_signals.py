"""
Unit tests for signals/fundamental.py and data/fundamental.py.

Tests verify:
  - FundamentalData construction (typed dataclass)
  - fetch_fundamental_data() routing through provider (mocked)
  - Every metric method in isolation:
      PE ratio, forward PE trend, PB ratio, ROE, profit margin,
      revenue growth, earnings growth, debt-to-equity, current ratio,
      dividend yield
  - Each metric at every level (STRONG BULLISH → STRONG BEARISH)
  - Missing data (None) → signal skipped
  - Invalid data (negative PE, negative D/E) → signal skipped
  - Category is always FUNDAMENTAL
  - Timeframe is correct per metric (LONG / MEDIUM)
  - EngineResult aggregation via EngineResult.from_signals()
  - Signal IDs are unique within a single EngineResult
  - to_dict() shape and content
  - Empty FundamentalData → empty EngineResult (NEUTRAL, 0 signals)
  - Crypto skip: fetch_fundamental_data() returns None for CRYPTOCURRENCY quoteType

No network calls; all yfinance interactions are mocked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from unittest.mock import patch
import pytest

from data.fundamental import FundamentalData, fetch_fundamental_data
from signals.fundamental import FundamentalSignalEngine, _contribution, _strength
from signals.fundamental_config import (
    PE_STRONG_BULL_THRESHOLD, PE_BULL_THRESHOLD,
    PE_BEAR_THRESHOLD, PE_STRONG_BEAR_THRESHOLD, PE_MAX_CONTRIBUTION,
    PB_STRONG_BULL_THRESHOLD, PB_BULL_THRESHOLD,
    PB_BEAR_THRESHOLD, PB_STRONG_BEAR_THRESHOLD, PB_MAX_CONTRIBUTION,
    ROE_STRONG_BULL_THRESHOLD, ROE_BULL_THRESHOLD,
    ROE_BEAR_THRESHOLD, ROE_STRONG_BEAR_THRESHOLD, ROE_MAX_CONTRIBUTION,
    MARGIN_STRONG_BULL_THRESHOLD, MARGIN_BULL_THRESHOLD,
    MARGIN_BEAR_THRESHOLD, MARGIN_STRONG_BEAR_THRESHOLD, MARGIN_MAX_CONTRIBUTION,
    REV_STRONG_BULL_THRESHOLD, REV_BULL_THRESHOLD,
    REV_BEAR_THRESHOLD, REV_STRONG_BEAR_THRESHOLD, REV_MAX_CONTRIBUTION,
    EPS_STRONG_BULL_THRESHOLD, EPS_BULL_THRESHOLD,
    EPS_BEAR_THRESHOLD, EPS_STRONG_BEAR_THRESHOLD, EPS_MAX_CONTRIBUTION,
    DE_STRONG_BULL_THRESHOLD, DE_BULL_THRESHOLD,
    DE_BEAR_THRESHOLD, DE_STRONG_BEAR_THRESHOLD, DE_MAX_CONTRIBUTION,
    CR_STRONG_BULL_THRESHOLD, CR_BULL_THRESHOLD,
    CR_BEAR_THRESHOLD, CR_STRONG_BEAR_THRESHOLD, CR_MAX_CONTRIBUTION,
    DIV_STRONG_BULL_THRESHOLD, DIV_BULL_THRESHOLD, DIV_WEAK_THRESHOLD,
    DIV_MAX_CONTRIBUTION,
    SCALE_STRONG, SCALE_MODERATE,
    NORM_STRONG_BULLISH, NORM_BULLISH, NORM_NEUTRAL, NORM_BEARISH, NORM_STRONG_BEARISH,
    FORWARD_PE_BULL_RATIO, FORWARD_PE_BEAR_RATIO, FORWARD_PE_MAX_CONTRIBUTION,
)
from signals.models import EngineResult


# ── Shared engine instance ────────────────────────────────────────────────────

ENGINE = FundamentalSignalEngine()


def _empty() -> FundamentalData:
    return FundamentalData(symbol="TEST")


def _data(**kwargs) -> FundamentalData:
    return FundamentalData(symbol="TEST", **kwargs)


# ── FundamentalData dataclass ─────────────────────────────────────────────────

class TestFundamentalData:
    def test_all_none_by_default(self):
        d = _empty()
        assert d.pe_ratio is None
        assert d.roe is None
        assert d.debt_to_equity is None

    def test_symbol_stored(self):
        d = _data(pe_ratio=15.0)
        assert d.symbol == "TEST"

    def test_values_stored(self):
        d = _data(pe_ratio=12.0, roe=0.18, profit_margin=0.12)
        assert d.pe_ratio == 12.0
        assert d.roe == 0.18
        assert d.profit_margin == 0.12


# ── Helper functions ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_contribution_bullish_scale_strong(self):
        assert _contribution("BULLISH", SCALE_STRONG, 10.0) == 10.0

    def test_contribution_bullish_scale_moderate(self):
        assert _contribution("BULLISH", SCALE_MODERATE, 10.0) == 6.0

    def test_contribution_bearish_scale_strong(self):
        assert _contribution("BEARISH", SCALE_STRONG, 10.0) == -10.0

    def test_contribution_bearish_scale_moderate(self):
        assert _contribution("BEARISH", SCALE_MODERATE, 10.0) == -6.0

    def test_contribution_neutral_zero(self):
        assert _contribution("NEUTRAL", 0.0, 10.0) == 0.0

    def test_strength_strong(self):
        assert _strength(SCALE_STRONG) == "STRONG"

    def test_strength_moderate(self):
        assert _strength(SCALE_MODERATE) == "MODERATE"

    def test_strength_weak(self):
        assert _strength(0.0) == "WEAK"


# ── PE Ratio signals ──────────────────────────────────────────────────────────

class TestPERatioSignal:
    def _pe(self, v):
        return ENGINE._signal_pe_ratio(_data(pe_ratio=v))

    def test_deeply_undervalued_is_strong_bullish(self):
        sig = self._pe(PE_STRONG_BULL_THRESHOLD - 1)
        assert sig.direction == "BULLISH"
        assert sig.strength == "STRONG"
        assert sig.normalized_value == NORM_STRONG_BULLISH
        assert sig.contribution == PE_MAX_CONTRIBUTION

    def test_undervalued_is_moderate_bullish(self):
        sig = self._pe((PE_STRONG_BULL_THRESHOLD + PE_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"
        assert sig.strength == "MODERATE"
        assert sig.normalized_value == NORM_BULLISH

    def test_fairly_valued_is_neutral(self):
        sig = self._pe((PE_BULL_THRESHOLD + PE_BEAR_THRESHOLD) / 2)
        assert sig.direction == "NEUTRAL"
        assert sig.contribution == 0.0
        assert sig.normalized_value == NORM_NEUTRAL

    def test_moderately_overvalued_is_bearish(self):
        sig = self._pe((PE_BEAR_THRESHOLD + PE_STRONG_BEAR_THRESHOLD) / 2)
        assert sig.direction == "BEARISH"
        assert sig.strength == "MODERATE"
        assert sig.normalized_value == NORM_BEARISH

    def test_significantly_overvalued_is_strong_bearish(self):
        sig = self._pe(PE_STRONG_BEAR_THRESHOLD + 5)
        assert sig.direction == "BEARISH"
        assert sig.strength == "STRONG"
        assert sig.normalized_value == NORM_STRONG_BEARISH
        assert sig.contribution == -PE_MAX_CONTRIBUTION

    def test_missing_pe_returns_none(self):
        assert ENGINE._signal_pe_ratio(_empty()) is None

    def test_negative_pe_returns_none(self):
        assert self._pe(-5.0) is None

    def test_zero_pe_returns_none(self):
        assert self._pe(0.0) is None

    def test_category_is_fundamental(self):
        sig = self._pe(12.0)
        assert sig.category == "FUNDAMENTAL"

    def test_timeframe_is_long(self):
        sig = self._pe(12.0)
        assert sig.timeframe == "LONG"

    def test_signal_id_contains_direction(self):
        sig = self._pe(8.0)
        assert "bullish" in sig.signal_id

    def test_value_preserved(self):
        sig = self._pe(12.5)
        assert sig.value == 12.5


# ── Forward PE trend signals ──────────────────────────────────────────────────

class TestForwardPETrendSignal:
    def _fpe(self, trailing, forward):
        return ENGINE._signal_forward_pe_trend(_data(pe_ratio=trailing, forward_pe=forward))

    def test_forward_much_lower_is_bullish(self):
        sig = self._fpe(20.0, 20.0 * (FORWARD_PE_BULL_RATIO - 0.05))
        assert sig.direction == "BULLISH"

    def test_forward_much_higher_is_bearish(self):
        sig = self._fpe(20.0, 20.0 * (FORWARD_PE_BEAR_RATIO + 0.05))
        assert sig.direction == "BEARISH"

    def test_similar_values_returns_none(self):
        # Within the neutral zone
        assert self._fpe(20.0, 20.0) is None

    def test_missing_trailing_returns_none(self):
        assert ENGINE._signal_forward_pe_trend(_data(forward_pe=15.0)) is None

    def test_missing_forward_returns_none(self):
        assert ENGINE._signal_forward_pe_trend(_data(pe_ratio=20.0)) is None

    def test_timeframe_is_medium(self):
        sig = self._fpe(20.0, 15.0)
        assert sig.timeframe == "MEDIUM"


# ── PB Ratio signals ──────────────────────────────────────────────────────────

class TestPBRatioSignal:
    def _pb(self, v):
        return ENGINE._signal_pb_ratio(_data(pb_ratio=v))

    def test_below_book_is_strong_bullish(self):
        sig = self._pb(PB_STRONG_BULL_THRESHOLD - 0.1)
        assert sig.direction == "BULLISH"
        assert sig.strength == "STRONG"

    def test_moderate_premium_is_bullish(self):
        sig = self._pb((PB_STRONG_BULL_THRESHOLD + PB_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"
        assert sig.strength == "MODERATE"

    def test_fair_premium_is_neutral(self):
        sig = self._pb((PB_BULL_THRESHOLD + PB_BEAR_THRESHOLD) / 2)
        assert sig.direction == "NEUTRAL"

    def test_high_premium_is_bearish(self):
        sig = self._pb((PB_BEAR_THRESHOLD + PB_STRONG_BEAR_THRESHOLD) / 2)
        assert sig.direction == "BEARISH"
        assert sig.strength == "MODERATE"

    def test_very_high_premium_is_strong_bearish(self):
        sig = self._pb(PB_STRONG_BEAR_THRESHOLD + 1)
        assert sig.direction == "BEARISH"
        assert sig.strength == "STRONG"

    def test_missing_pb_returns_none(self):
        assert ENGINE._signal_pb_ratio(_empty()) is None

    def test_negative_pb_returns_none(self):
        assert self._pb(-0.5) is None


# ── ROE signals ───────────────────────────────────────────────────────────────

class TestROESignal:
    def _roe(self, v):
        return ENGINE._signal_roe(_data(roe=v))

    def test_excellent_roe_is_strong_bullish(self):
        sig = self._roe(ROE_STRONG_BULL_THRESHOLD + 0.05)
        assert sig.direction == "BULLISH"
        assert sig.strength == "STRONG"
        assert sig.contribution == ROE_MAX_CONTRIBUTION

    def test_good_roe_is_moderate_bullish(self):
        sig = self._roe((ROE_STRONG_BULL_THRESHOLD + ROE_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"
        assert sig.strength == "MODERATE"

    def test_adequate_roe_is_neutral(self):
        sig = self._roe((ROE_BULL_THRESHOLD + ROE_BEAR_THRESHOLD) / 2)
        assert sig.direction == "NEUTRAL"

    def test_weak_roe_is_bearish(self):
        sig = self._roe((ROE_BEAR_THRESHOLD + ROE_STRONG_BEAR_THRESHOLD) / 2)
        assert sig.direction == "BEARISH"
        assert sig.strength == "MODERATE"

    def test_poor_roe_is_strong_bearish(self):
        sig = self._roe(ROE_STRONG_BEAR_THRESHOLD - 0.02)
        assert sig.direction == "BEARISH"
        assert sig.strength == "STRONG"
        assert sig.contribution == -ROE_MAX_CONTRIBUTION

    def test_missing_roe_returns_none(self):
        assert ENGINE._signal_roe(_empty()) is None

    def test_negative_roe_is_bearish(self):
        # Negative ROE = company losing money
        sig = self._roe(-0.10)
        assert sig.direction == "BEARISH"


# ── Profit Margin signals ─────────────────────────────────────────────────────

class TestProfitMarginSignal:
    def _pm(self, v):
        return ENGINE._signal_profit_margin(_data(profit_margin=v))

    def test_high_margin_strong_bullish(self):
        sig = self._pm(MARGIN_STRONG_BULL_THRESHOLD + 0.05)
        assert sig.direction == "BULLISH"
        assert sig.strength == "STRONG"

    def test_solid_margin_moderate_bullish(self):
        sig = self._pm((MARGIN_STRONG_BULL_THRESHOLD + MARGIN_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"
        assert sig.strength == "MODERATE"

    def test_moderate_margin_neutral(self):
        sig = self._pm((MARGIN_BULL_THRESHOLD + MARGIN_BEAR_THRESHOLD) / 2)
        assert sig.direction == "NEUTRAL"

    def test_thin_margin_bearish(self):
        sig = self._pm((MARGIN_BEAR_THRESHOLD + MARGIN_STRONG_BEAR_THRESHOLD) / 2)
        assert sig.direction == "BEARISH"
        assert sig.strength == "MODERATE"

    def test_near_breakeven_strong_bearish(self):
        sig = self._pm(MARGIN_STRONG_BEAR_THRESHOLD - 0.005)
        assert sig.direction == "BEARISH"
        assert sig.strength == "STRONG"

    def test_missing_margin_returns_none(self):
        assert ENGINE._signal_profit_margin(_empty()) is None


# ── Revenue Growth signals ────────────────────────────────────────────────────

class TestRevenueGrowthSignal:
    def _rg(self, v):
        return ENGINE._signal_revenue_growth(_data(revenue_growth=v))

    def test_strong_growth_is_strong_bullish(self):
        sig = self._rg(REV_STRONG_BULL_THRESHOLD + 0.05)
        assert sig.direction == "BULLISH"
        assert sig.strength == "STRONG"

    def test_healthy_growth_is_moderate_bullish(self):
        sig = self._rg((REV_STRONG_BULL_THRESHOLD + REV_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"
        assert sig.strength == "MODERATE"

    def test_stable_growth_is_neutral(self):
        sig = self._rg((REV_BULL_THRESHOLD + REV_BEAR_THRESHOLD) / 2)
        assert sig.direction == "NEUTRAL"

    def test_mild_contraction_is_bearish(self):
        sig = self._rg((REV_BEAR_THRESHOLD + REV_STRONG_BEAR_THRESHOLD) / 2)
        assert sig.direction == "BEARISH"
        assert sig.strength == "MODERATE"

    def test_significant_decline_is_strong_bearish(self):
        sig = self._rg(REV_STRONG_BEAR_THRESHOLD - 0.05)
        assert sig.direction == "BEARISH"
        assert sig.strength == "STRONG"

    def test_timeframe_is_medium(self):
        sig = self._rg(0.25)
        assert sig.timeframe == "MEDIUM"

    def test_missing_revenue_growth_returns_none(self):
        assert ENGINE._signal_revenue_growth(_empty()) is None


# ── Earnings Growth signals ───────────────────────────────────────────────────

class TestEarningsGrowthSignal:
    def _eg(self, v):
        return ENGINE._signal_earnings_growth(_data(earnings_growth=v))

    def test_strong_growth_strong_bullish(self):
        assert self._eg(EPS_STRONG_BULL_THRESHOLD + 0.05).direction == "BULLISH"
        assert self._eg(EPS_STRONG_BULL_THRESHOLD + 0.05).strength == "STRONG"

    def test_solid_growth_moderate_bullish(self):
        sig = self._eg((EPS_STRONG_BULL_THRESHOLD + EPS_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"

    def test_flat_earnings_neutral(self):
        sig = self._eg((EPS_BULL_THRESHOLD + EPS_BEAR_THRESHOLD) / 2)
        assert sig.direction == "NEUTRAL"

    def test_mild_decline_bearish(self):
        sig = self._eg((EPS_BEAR_THRESHOLD + EPS_STRONG_BEAR_THRESHOLD) / 2)
        assert sig.direction == "BEARISH"

    def test_significant_decline_strong_bearish(self):
        sig = self._eg(EPS_STRONG_BEAR_THRESHOLD - 0.05)
        assert sig.direction == "BEARISH"
        assert sig.strength == "STRONG"

    def test_missing_earnings_growth_returns_none(self):
        assert ENGINE._signal_earnings_growth(_empty()) is None


# ── Debt-to-Equity signals ────────────────────────────────────────────────────

class TestDebtToEquitySignal:
    def _de(self, v):
        return ENGINE._signal_debt_to_equity(_data(debt_to_equity=v))

    def test_very_low_debt_strong_bullish(self):
        sig = self._de(DE_STRONG_BULL_THRESHOLD - 0.1)
        assert sig.direction == "BULLISH"
        assert sig.strength == "STRONG"

    def test_manageable_debt_moderate_bullish(self):
        sig = self._de((DE_STRONG_BULL_THRESHOLD + DE_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"
        assert sig.strength == "MODERATE"

    def test_moderate_leverage_neutral(self):
        sig = self._de((DE_BULL_THRESHOLD + DE_BEAR_THRESHOLD) / 2)
        assert sig.direction == "NEUTRAL"

    def test_elevated_debt_bearish(self):
        sig = self._de((DE_BEAR_THRESHOLD + DE_STRONG_BEAR_THRESHOLD) / 2)
        assert sig.direction == "BEARISH"
        assert sig.strength == "MODERATE"

    def test_high_debt_strong_bearish(self):
        sig = self._de(DE_STRONG_BEAR_THRESHOLD + 0.5)
        assert sig.direction == "BEARISH"
        assert sig.strength == "STRONG"
        assert sig.contribution == -DE_MAX_CONTRIBUTION

    def test_missing_de_returns_none(self):
        assert ENGINE._signal_debt_to_equity(_empty()) is None

    def test_negative_de_returns_none(self):
        assert self._de(-1.0) is None


# ── Current Ratio signals ─────────────────────────────────────────────────────

class TestCurrentRatioSignal:
    def _cr(self, v):
        return ENGINE._signal_current_ratio(_data(current_ratio=v))

    def test_strong_liquidity_strong_bullish(self):
        sig = self._cr(CR_STRONG_BULL_THRESHOLD + 0.5)
        assert sig.direction == "BULLISH"
        assert sig.strength == "STRONG"

    def test_solid_liquidity_moderate_bullish(self):
        sig = self._cr((CR_STRONG_BULL_THRESHOLD + CR_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"
        assert sig.strength == "MODERATE"

    def test_adequate_liquidity_neutral(self):
        sig = self._cr((CR_BULL_THRESHOLD + CR_BEAR_THRESHOLD) / 2)
        assert sig.direction == "NEUTRAL"

    def test_pressure_bearish(self):
        sig = self._cr((CR_BEAR_THRESHOLD + CR_STRONG_BEAR_THRESHOLD) / 2)
        assert sig.direction == "BEARISH"
        assert sig.strength == "MODERATE"

    def test_poor_liquidity_strong_bearish(self):
        sig = self._cr(CR_STRONG_BEAR_THRESHOLD - 0.1)
        assert sig.direction == "BEARISH"
        assert sig.strength == "STRONG"

    def test_timeframe_is_medium(self):
        sig = self._cr(3.0)
        assert sig.timeframe == "MEDIUM"

    def test_missing_cr_returns_none(self):
        assert ENGINE._signal_current_ratio(_empty()) is None


# ── Dividend Yield signals ────────────────────────────────────────────────────

class TestDividendYieldSignal:
    def _div(self, v):
        return ENGINE._signal_dividend_yield(_data(dividend_yield=v))

    def test_high_yield_strong_bullish(self):
        sig = self._div(DIV_STRONG_BULL_THRESHOLD + 0.01)
        assert sig.direction == "BULLISH"
        assert sig.strength == "STRONG"
        assert sig.contribution == DIV_MAX_CONTRIBUTION

    def test_moderate_yield_moderate_bullish(self):
        sig = self._div((DIV_STRONG_BULL_THRESHOLD + DIV_BULL_THRESHOLD) / 2)
        assert sig.direction == "BULLISH"
        assert sig.strength == "MODERATE"

    def test_negligible_yield_returns_none(self):
        assert self._div(DIV_WEAK_THRESHOLD - 0.001) is None

    def test_zero_yield_returns_none(self):
        assert self._div(0.0) is None

    def test_missing_yield_returns_none(self):
        assert ENGINE._signal_dividend_yield(_empty()) is None

    def test_always_bullish_never_bearish(self):
        # Dividend yield can only generate BULLISH signals
        for v in [0.025, 0.035, 0.06, 0.08]:
            sig = self._div(v)
            assert sig is None or sig.direction == "BULLISH"


# ── Full generate() ───────────────────────────────────────────────────────────

class TestGenerateMethod:
    def test_empty_data_returns_neutral_engine_result(self):
        result = ENGINE.generate(_empty())
        assert result.direction == "NEUTRAL"
        assert result.signals == []
        assert result.aggregate_score == 0.0
        assert result.engine == "FUNDAMENTAL"

    def test_all_bullish_data_returns_bullish_result(self):
        data = _data(
            pe_ratio=8.0,
            pb_ratio=0.8,
            roe=0.25,
            profit_margin=0.22,
            revenue_growth=0.25,
            earnings_growth=0.25,
            debt_to_equity=0.2,
            current_ratio=3.0,
            dividend_yield=0.06,
        )
        result = ENGINE.generate(data)
        assert result.direction == "BULLISH"
        assert result.aggregate_score > 0

    def test_all_bearish_data_returns_bearish_result(self):
        data = _data(
            pe_ratio=50.0,
            pb_ratio=7.0,
            roe=-0.05,
            profit_margin=-0.02,
            revenue_growth=-0.10,
            earnings_growth=-0.10,
            debt_to_equity=3.5,
            current_ratio=0.5,
        )
        result = ENGINE.generate(data)
        assert result.direction == "BEARISH"
        assert result.aggregate_score < 0

    def test_mixed_data_returns_result_with_signals(self):
        data = _data(
            pe_ratio=12.0,
            roe=0.25,
            debt_to_equity=2.0,
        )
        result = ENGINE.generate(data)
        assert len(result.signals) == 3  # one per non-None metric

    def test_crypto_data_with_no_fundamentals_returns_empty(self):
        # All None → 0 signals
        result = ENGINE.generate(_empty())
        assert len(result.signals) == 0

    def test_signal_ids_unique(self):
        data = _data(
            pe_ratio=12.0,
            pb_ratio=1.5,
            roe=0.18,
            profit_margin=0.12,
            revenue_growth=0.15,
            earnings_growth=0.18,
            debt_to_equity=0.5,
            current_ratio=2.0,
            dividend_yield=0.04,
        )
        result = ENGINE.generate(data)
        ids = [s.signal_id for s in result.signals]
        assert len(ids) == len(set(ids)), f"Duplicate signal IDs: {ids}"

    def test_all_signals_have_fundamental_category(self):
        data = _data(
            pe_ratio=12.0, pb_ratio=1.5, roe=0.18,
            revenue_growth=0.15, debt_to_equity=0.5,
        )
        result = ENGINE.generate(data)
        for sig in result.signals:
            assert sig.category == "FUNDAMENTAL", f"{sig.signal_id} has wrong category"

    def test_confidence_in_valid_range(self):
        data = _data(pe_ratio=12.0, roe=0.18, revenue_growth=0.15)
        result = ENGINE.generate(data)
        assert 0.0 <= result.confidence <= 1.0

    def test_aggregate_score_is_sum_of_contributions(self):
        data = _data(
            pe_ratio=8.0,      # STRONG BULLISH → +PE_MAX_CONTRIBUTION
            roe=-0.05,         # STRONG BEARISH → -ROE_MAX_CONTRIBUTION
        )
        result = ENGINE.generate(data)
        expected = sum(s.contribution for s in result.signals)
        assert abs(result.aggregate_score - expected) < 0.01

    def test_neutral_signals_dont_count_toward_direction(self):
        # All neutral metrics → NEUTRAL direction
        data = _data(
            pe_ratio=20.0,         # NEUTRAL (between bull and bear thresholds)
            pb_ratio=2.5,          # NEUTRAL
        )
        result = ENGINE.generate(data)
        assert result.direction == "NEUTRAL"

    def test_to_dict_has_correct_keys(self):
        result = ENGINE.generate(_data(pe_ratio=12.0))
        d = result.to_dict()
        assert "engine" in d
        assert "aggregate_score" in d
        assert "direction" in d
        assert "confidence" in d
        assert "signal_count" in d
        assert "signals" in d
        assert d["engine"] == "FUNDAMENTAL"

    def test_signal_count_matches_signals_list(self):
        result = ENGINE.generate(_data(pe_ratio=12.0, roe=0.18))
        d = result.to_dict()
        assert d["signal_count"] == len(d["signals"])

    def test_forward_pe_trend_bullish_included(self):
        # forward < trailing * FORWARD_PE_BULL_RATIO
        data = _data(pe_ratio=20.0, forward_pe=17.0)
        result = ENGINE.generate(data)
        fwd_signals = [s for s in result.signals if "forward_pe" in s.signal_id]
        assert len(fwd_signals) == 1
        assert fwd_signals[0].direction == "BULLISH"


# ── fetch_fundamental_data() ──────────────────────────────────────────────────

class TestFetchFundamentalData:
    def _make_info(self, **overrides):
        base = {
            "quoteType": "EQUITY",
            "trailingPE": 15.0,
            "priceToBook": 2.0,
            "returnOnEquity": 0.18,
            "profitMargins": 0.12,
            "revenueGrowth": 0.10,
            "earningsGrowth": 0.15,
            "debtToEquity": 0.8,
            "currentRatio": 1.8,
            "dividendYield": 0.025,
            "forwardPE": 14.0,
        }
        base.update(overrides)
        return base

    def test_returns_fundamental_data_for_equity(self):
        with patch("data.fetcher.fetch_info", return_value=self._make_info()):
            result = fetch_fundamental_data("AAPL")
        assert result is not None
        assert isinstance(result, FundamentalData)
        assert result.symbol == "AAPL"

    def test_returns_none_for_crypto(self):
        with patch("data.fetcher.fetch_info", return_value={"quoteType": "CRYPTOCURRENCY"}):
            assert fetch_fundamental_data("BTC-USD") is None

    def test_returns_none_for_empty_info(self):
        with patch("data.fetcher.fetch_info", return_value={}):
            assert fetch_fundamental_data("UNKNOWN") is None

    def test_returns_none_on_exception(self):
        with patch("data.fetcher.fetch_info", side_effect=Exception("network error")):
            assert fetch_fundamental_data("ERR") is None

    def test_pe_ratio_mapped_correctly(self):
        with patch("data.fetcher.fetch_info", return_value=self._make_info(trailingPE=22.5)):
            result = fetch_fundamental_data("AAPL")
        assert result.pe_ratio == 22.5

    def test_nan_value_mapped_to_none(self):
        import math
        with patch("data.fetcher.fetch_info", return_value=self._make_info(trailingPE=float("nan"))):
            result = fetch_fundamental_data("AAPL")
        assert result.pe_ratio is None

    def test_none_field_stays_none(self):
        info = self._make_info()
        info.pop("debtToEquity", None)
        with patch("data.fetcher.fetch_info", return_value=info):
            result = fetch_fundamental_data("AAPL")
        assert result.debt_to_equity is None

    def test_roe_mapped_as_decimal(self):
        with patch("data.fetcher.fetch_info", return_value=self._make_info(returnOnEquity=0.22)):
            result = fetch_fundamental_data("AAPL")
        assert result.roe == 0.22
