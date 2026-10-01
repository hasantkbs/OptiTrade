"""
Fundamental Signal Engine — Phase B1
======================================
Generates structured Signal objects from a FundamentalData snapshot.

This engine is completely independent from TechnicalSignalEngine:
  - It takes FundamentalData, not scoring contributions.
  - It generates its own signals from scratch.
  - It never modifies the existing score.
  - Each metric method is independently testable.

Design principles:
  - Every private _signal_*() method returns Optional[Signal].
    None means "data missing or not signal-worthy — skip silently."
  - All thresholds live in fundamental_config.py — never hardcoded here.
  - Aggregation uses EngineResult.from_signals() — shared with TechnicalEngine.
  - Contribution values are independent of the technical score scale;
    they exist solely for the DecisionEngine (future phase) to weigh engines.
"""
from typing import List, Optional

from data.fundamental import FundamentalData
from signals.models import EngineResult, Signal
from signals.fundamental_config import (
    # PE
    PE_STRONG_BULL_THRESHOLD, PE_BULL_THRESHOLD,
    PE_BEAR_THRESHOLD, PE_STRONG_BEAR_THRESHOLD,
    PE_MAX_CONTRIBUTION, PE_CONFIDENCE,
    # Forward PE
    FORWARD_PE_BULL_RATIO, FORWARD_PE_BEAR_RATIO,
    FORWARD_PE_MAX_CONTRIBUTION, FORWARD_PE_CONFIDENCE,
    # PB
    PB_STRONG_BULL_THRESHOLD, PB_BULL_THRESHOLD,
    PB_BEAR_THRESHOLD, PB_STRONG_BEAR_THRESHOLD,
    PB_MAX_CONTRIBUTION, PB_CONFIDENCE,
    # ROE
    ROE_STRONG_BULL_THRESHOLD, ROE_BULL_THRESHOLD,
    ROE_BEAR_THRESHOLD, ROE_STRONG_BEAR_THRESHOLD,
    ROE_MAX_CONTRIBUTION, ROE_CONFIDENCE,
    # Profit margin
    MARGIN_STRONG_BULL_THRESHOLD, MARGIN_BULL_THRESHOLD,
    MARGIN_BEAR_THRESHOLD, MARGIN_STRONG_BEAR_THRESHOLD,
    MARGIN_MAX_CONTRIBUTION, MARGIN_CONFIDENCE,
    # Revenue growth
    REV_STRONG_BULL_THRESHOLD, REV_BULL_THRESHOLD,
    REV_BEAR_THRESHOLD, REV_STRONG_BEAR_THRESHOLD,
    REV_MAX_CONTRIBUTION, REV_CONFIDENCE,
    # Earnings growth
    EPS_STRONG_BULL_THRESHOLD, EPS_BULL_THRESHOLD,
    EPS_BEAR_THRESHOLD, EPS_STRONG_BEAR_THRESHOLD,
    EPS_MAX_CONTRIBUTION, EPS_CONFIDENCE,
    # Debt-to-equity
    DE_STRONG_BULL_THRESHOLD, DE_BULL_THRESHOLD,
    DE_BEAR_THRESHOLD, DE_STRONG_BEAR_THRESHOLD,
    DE_MAX_CONTRIBUTION, DE_CONFIDENCE,
    # Current ratio
    CR_STRONG_BULL_THRESHOLD, CR_BULL_THRESHOLD,
    CR_BEAR_THRESHOLD, CR_STRONG_BEAR_THRESHOLD,
    CR_MAX_CONTRIBUTION, CR_CONFIDENCE,
    # Dividend yield
    DIV_STRONG_BULL_THRESHOLD, DIV_BULL_THRESHOLD, DIV_WEAK_THRESHOLD,
    DIV_MAX_CONTRIBUTION, DIV_CONFIDENCE,
    # Scale + normalized value constants
    SCALE_STRONG, SCALE_MODERATE,
    NORM_STRONG_BULLISH, NORM_BULLISH, NORM_NEUTRAL,
    NORM_BEARISH, NORM_STRONG_BEARISH,
)

_CATEGORY  = "FUNDAMENTAL"
_TIMEFRAME_LONG   = "LONG"
_TIMEFRAME_MEDIUM = "MEDIUM"


class FundamentalSignalEngine:
    """
    Converts a FundamentalData snapshot into an EngineResult.

    Each metric produces at most one Signal.  Missing data (None) is
    silently skipped — a missing metric contributes neither BULLISH nor
    BEARISH weight to the aggregate.
    """

    def generate(self, data: FundamentalData) -> EngineResult:
        """
        Generate fundamental signals for the given data snapshot.

        Parameters
        ----------
        data : FundamentalData
            Snapshot as returned by data.fundamental.fetch_fundamental_data().

        Returns
        -------
        EngineResult  with one Signal per available metric.
        """
        signals: List[Signal] = list(filter(None, [
            self._signal_pe_ratio(data),
            self._signal_forward_pe_trend(data),
            self._signal_pb_ratio(data),
            self._signal_roe(data),
            self._signal_profit_margin(data),
            self._signal_revenue_growth(data),
            self._signal_earnings_growth(data),
            self._signal_debt_to_equity(data),
            self._signal_current_ratio(data),
            self._signal_dividend_yield(data),
        ]))
        return EngineResult.from_signals("FUNDAMENTAL", signals)

    # ── Individual metric signal generators ───────────────────────────────────

    def _signal_pe_ratio(self, data: FundamentalData) -> Optional[Signal]:
        v = data.pe_ratio
        if v is None or v <= 0:
            return None  # Negative PE (loss-making) is not comparable

        if v < PE_STRONG_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"P/E {v:.1f}x — deeply undervalued relative to earnings"
        elif v < PE_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"P/E {v:.1f}x — below 15x suggests undervaluation"
        elif v <= PE_BEAR_THRESHOLD:
            direction, norm, scale = "NEUTRAL", NORM_NEUTRAL, 0.0
            reason = f"P/E {v:.1f}x — fairly valued"
        elif v <= PE_STRONG_BEAR_THRESHOLD:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"P/E {v:.1f}x — moderately overvalued"
        else:
            direction, norm, scale = "BEARISH", NORM_STRONG_BEARISH, SCALE_STRONG
            reason = f"P/E {v:.1f}x — significantly overvalued"

        contribution = _contribution(direction, scale, PE_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"pe_ratio_{direction.lower()}",
            indicator        = "PE Ratio",
            value            = v,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = PE_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_LONG,
            category         = _CATEGORY,
        )

    def _signal_forward_pe_trend(self, data: FundamentalData) -> Optional[Signal]:
        trailing = data.pe_ratio
        forward  = data.forward_pe
        if trailing is None or forward is None or trailing <= 0 or forward <= 0:
            return None

        ratio = forward / trailing
        if ratio < FORWARD_PE_BULL_RATIO:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"Forward P/E ({forward:.1f}x) < Trailing ({trailing:.1f}x) — earnings expected to grow"
        elif ratio > FORWARD_PE_BEAR_RATIO:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"Forward P/E ({forward:.1f}x) > Trailing ({trailing:.1f}x) — earnings expected to shrink"
        else:
            return None  # Negligible difference — not signal-worthy

        contribution = _contribution(direction, scale, FORWARD_PE_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"forward_pe_trend_{direction.lower()}",
            indicator        = "Forward PE Trend",
            value            = forward,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = FORWARD_PE_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_MEDIUM,
            category         = _CATEGORY,
        )

    def _signal_pb_ratio(self, data: FundamentalData) -> Optional[Signal]:
        v = data.pb_ratio
        if v is None or v <= 0:
            return None

        if v < PB_STRONG_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"P/B {v:.2f}x — trading below book value"
        elif v < PB_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"P/B {v:.2f}x — moderate book-value premium"
        elif v <= PB_BEAR_THRESHOLD:
            direction, norm, scale = "NEUTRAL", NORM_NEUTRAL, 0.0
            reason = f"P/B {v:.2f}x — fairly priced relative to book"
        elif v <= PB_STRONG_BEAR_THRESHOLD:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"P/B {v:.2f}x — high book-value premium"
        else:
            direction, norm, scale = "BEARISH", NORM_STRONG_BEARISH, SCALE_STRONG
            reason = f"P/B {v:.2f}x — very high book-value premium"

        contribution = _contribution(direction, scale, PB_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"pb_ratio_{direction.lower()}",
            indicator        = "PB Ratio",
            value            = v,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = PB_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_LONG,
            category         = _CATEGORY,
        )

    def _signal_roe(self, data: FundamentalData) -> Optional[Signal]:
        v = data.roe
        if v is None:
            return None

        if v >= ROE_STRONG_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"ROE {v*100:.1f}% — excellent capital efficiency"
        elif v >= ROE_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"ROE {v*100:.1f}% — above-average capital returns"
        elif v >= ROE_BEAR_THRESHOLD:
            direction, norm, scale = "NEUTRAL", NORM_NEUTRAL, 0.0
            reason = f"ROE {v*100:.1f}% — adequate capital efficiency"
        elif v >= ROE_STRONG_BEAR_THRESHOLD:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"ROE {v*100:.1f}% — weak capital returns"
        else:
            direction, norm, scale = "BEARISH", NORM_STRONG_BEARISH, SCALE_STRONG
            reason = f"ROE {v*100:.1f}% — poor capital efficiency"

        contribution = _contribution(direction, scale, ROE_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"roe_{direction.lower()}",
            indicator        = "ROE",
            value            = v,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = ROE_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_LONG,
            category         = _CATEGORY,
        )

    def _signal_profit_margin(self, data: FundamentalData) -> Optional[Signal]:
        v = data.profit_margin
        if v is None:
            return None

        if v >= MARGIN_STRONG_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"Net margin {v*100:.1f}% — highly profitable"
        elif v >= MARGIN_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"Net margin {v*100:.1f}% — solid profitability"
        elif v >= MARGIN_BEAR_THRESHOLD:
            direction, norm, scale = "NEUTRAL", NORM_NEUTRAL, 0.0
            reason = f"Net margin {v*100:.1f}% — moderate profitability"
        elif v >= MARGIN_STRONG_BEAR_THRESHOLD:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"Net margin {v*100:.1f}% — thin profitability"
        else:
            direction, norm, scale = "BEARISH", NORM_STRONG_BEARISH, SCALE_STRONG
            reason = f"Net margin {v*100:.1f}% — near break-even or loss"

        contribution = _contribution(direction, scale, MARGIN_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"profit_margin_{direction.lower()}",
            indicator        = "Profit Margin",
            value            = v,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = MARGIN_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_LONG,
            category         = _CATEGORY,
        )

    def _signal_revenue_growth(self, data: FundamentalData) -> Optional[Signal]:
        v = data.revenue_growth
        if v is None:
            return None

        if v >= REV_STRONG_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"Revenue growth +{v*100:.1f}% YoY — strong top-line expansion"
        elif v >= REV_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"Revenue growth +{v*100:.1f}% YoY — healthy expansion"
        elif v >= REV_BEAR_THRESHOLD:
            direction, norm, scale = "NEUTRAL", NORM_NEUTRAL, 0.0
            reason = f"Revenue growth {v*100:.1f}% YoY — stable but not accelerating"
        elif v >= REV_STRONG_BEAR_THRESHOLD:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"Revenue growth {v*100:.1f}% YoY — mild contraction"
        else:
            direction, norm, scale = "BEARISH", NORM_STRONG_BEARISH, SCALE_STRONG
            reason = f"Revenue growth {v*100:.1f}% YoY — significant decline"

        contribution = _contribution(direction, scale, REV_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"revenue_growth_{direction.lower()}",
            indicator        = "Revenue Growth",
            value            = v,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = REV_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_MEDIUM,
            category         = _CATEGORY,
        )

    def _signal_earnings_growth(self, data: FundamentalData) -> Optional[Signal]:
        v = data.earnings_growth
        if v is None:
            return None

        if v >= EPS_STRONG_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"Earnings growth +{v*100:.1f}% YoY — strong bottom-line expansion"
        elif v >= EPS_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"Earnings growth +{v*100:.1f}% YoY — solid profit growth"
        elif v >= EPS_BEAR_THRESHOLD:
            direction, norm, scale = "NEUTRAL", NORM_NEUTRAL, 0.0
            reason = f"Earnings growth {v*100:.1f}% YoY — flat earnings"
        elif v >= EPS_STRONG_BEAR_THRESHOLD:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"Earnings growth {v*100:.1f}% YoY — mild earnings decline"
        else:
            direction, norm, scale = "BEARISH", NORM_STRONG_BEARISH, SCALE_STRONG
            reason = f"Earnings growth {v*100:.1f}% YoY — significant earnings decline"

        contribution = _contribution(direction, scale, EPS_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"earnings_growth_{direction.lower()}",
            indicator        = "Earnings Growth",
            value            = v,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = EPS_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_MEDIUM,
            category         = _CATEGORY,
        )

    def _signal_debt_to_equity(self, data: FundamentalData) -> Optional[Signal]:
        v = data.debt_to_equity
        if v is None or v < 0:
            return None

        if v < DE_STRONG_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"D/E ratio {v:.2f} — minimal leverage, strong balance sheet"
        elif v < DE_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"D/E ratio {v:.2f} — manageable debt level"
        elif v <= DE_BEAR_THRESHOLD:
            direction, norm, scale = "NEUTRAL", NORM_NEUTRAL, 0.0
            reason = f"D/E ratio {v:.2f} — moderate leverage"
        elif v <= DE_STRONG_BEAR_THRESHOLD:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"D/E ratio {v:.2f} — elevated leverage increases risk"
        else:
            direction, norm, scale = "BEARISH", NORM_STRONG_BEARISH, SCALE_STRONG
            reason = f"D/E ratio {v:.2f} — high leverage, elevated financial risk"

        contribution = _contribution(direction, scale, DE_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"debt_to_equity_{direction.lower()}",
            indicator        = "Debt-to-Equity",
            value            = v,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = DE_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_LONG,
            category         = _CATEGORY,
        )

    def _signal_current_ratio(self, data: FundamentalData) -> Optional[Signal]:
        v = data.current_ratio
        if v is None or v < 0:
            return None

        if v >= CR_STRONG_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"Current ratio {v:.2f} — strong liquidity cushion"
        elif v >= CR_BULL_THRESHOLD:
            direction, norm, scale = "BULLISH", NORM_BULLISH, SCALE_MODERATE
            reason = f"Current ratio {v:.2f} — solid short-term liquidity"
        elif v >= CR_BEAR_THRESHOLD:
            direction, norm, scale = "NEUTRAL", NORM_NEUTRAL, 0.0
            reason = f"Current ratio {v:.2f} — adequate liquidity"
        elif v >= CR_STRONG_BEAR_THRESHOLD:
            direction, norm, scale = "BEARISH", NORM_BEARISH, SCALE_MODERATE
            reason = f"Current ratio {v:.2f} — liquidity under pressure"
        else:
            direction, norm, scale = "BEARISH", NORM_STRONG_BEARISH, SCALE_STRONG
            reason = f"Current ratio {v:.2f} — poor short-term liquidity"

        contribution = _contribution(direction, scale, CR_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = f"current_ratio_{direction.lower()}",
            indicator        = "Current Ratio",
            value            = v,
            normalized_value = norm,
            direction        = direction,
            strength         = _strength(scale),
            confidence       = CR_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_MEDIUM,
            category         = _CATEGORY,
        )

    def _signal_dividend_yield(self, data: FundamentalData) -> Optional[Signal]:
        v = data.dividend_yield
        if v is None or v < DIV_WEAK_THRESHOLD:
            return None  # No dividend or negligible yield — not signal-worthy

        if v >= DIV_STRONG_BULL_THRESHOLD:
            norm, scale = NORM_STRONG_BULLISH, SCALE_STRONG
            reason = f"Dividend yield {v*100:.1f}% — high income return"
        else:
            norm, scale = NORM_BULLISH, SCALE_MODERATE
            reason = f"Dividend yield {v*100:.1f}% — meaningful income component"

        contribution = _contribution("BULLISH", scale, DIV_MAX_CONTRIBUTION)
        return Signal(
            signal_id        = "dividend_yield_bullish",
            indicator        = "Dividend Yield",
            value            = v,
            normalized_value = norm,
            direction        = "BULLISH",
            strength         = _strength(scale),
            confidence       = DIV_CONFIDENCE,
            contribution     = contribution,
            reason           = reason,
            timeframe        = _TIMEFRAME_LONG,
            category         = _CATEGORY,
        )


# ── Module-level helpers ───────────────────────────────────────────────────────

def _contribution(direction: str, scale: float, max_contribution: float) -> float:
    """Return signed contribution: positive for BULLISH, negative for BEARISH."""
    if direction == "BULLISH":
        return round(scale * max_contribution, 1)
    if direction == "BEARISH":
        return round(-scale * max_contribution, 1)
    return 0.0


def _strength(scale: float) -> str:
    if scale >= SCALE_STRONG:
        return "STRONG"
    if scale >= SCALE_MODERATE:
        return "MODERATE"
    return "WEAK"
