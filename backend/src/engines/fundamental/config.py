"""
OptiTrade Fundamental Engine — configuration.

Centralizes the Feature Store feature names this engine reads/writes, so
`feature_adapter.py` and the six analyzer modules share one source of
truth for names.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# ── Valuation ───────────────────────────────────────────────────────────────
FEATURE_PE = "pe_ratio"
FEATURE_FORWARD_PE = "forward_pe_ratio"
FEATURE_PEG = "peg_ratio"
FEATURE_PRICE_TO_SALES = "price_to_sales"
FEATURE_PRICE_TO_BOOK = "price_to_book"
FEATURE_EV_TO_EBITDA = "ev_to_ebitda"

# ── Growth ──────────────────────────────────────────────────────────────────
FEATURE_REVENUE_GROWTH = "revenue_growth_pct"
FEATURE_EPS_GROWTH = "eps_growth_pct"
FEATURE_OPERATING_INCOME_GROWTH = "operating_income_growth_pct"
FEATURE_FCF_GROWTH = "fcf_growth_pct"

# ── Profitability ───────────────────────────────────────────────────────────
FEATURE_GROSS_MARGIN = "gross_margin_pct"
FEATURE_OPERATING_MARGIN = "operating_margin_pct"
FEATURE_NET_MARGIN = "net_margin_pct"
FEATURE_ROE = "roe_pct"
FEATURE_ROA = "roa_pct"
FEATURE_ROIC = "roic_pct"

# ── Financial Health ────────────────────────────────────────────────────────
FEATURE_DEBT_TO_EQUITY = "debt_to_equity_pct"
FEATURE_CURRENT_RATIO = "current_ratio"
FEATURE_QUICK_RATIO = "quick_ratio"
FEATURE_INTEREST_COVERAGE = "interest_coverage_ratio"
FEATURE_ALTMAN_Z = "altman_z_score"

# ── Cash Flow ───────────────────────────────────────────────────────────────
FEATURE_OCF_MARGIN = "operating_cash_flow_margin_pct"
FEATURE_FCF_MARGIN = "free_cash_flow_margin_pct"
FEATURE_CASH_CONVERSION = "cash_conversion_ratio"

# ── Business Quality ────────────────────────────────────────────────────────
FEATURE_EARNINGS_CONSISTENCY = "earnings_consistency_score"
FEATURE_MARGIN_STABILITY = "margin_stability_score"
FEATURE_CAPITAL_EFFICIENCY = "capital_efficiency_pct"
FEATURE_BALANCE_SHEET_QUALITY = "balance_sheet_quality_score"

ALL_FEATURE_NAMES = [
    FEATURE_PE, FEATURE_FORWARD_PE, FEATURE_PEG, FEATURE_PRICE_TO_SALES,
    FEATURE_PRICE_TO_BOOK, FEATURE_EV_TO_EBITDA,
    FEATURE_REVENUE_GROWTH, FEATURE_EPS_GROWTH,
    FEATURE_OPERATING_INCOME_GROWTH, FEATURE_FCF_GROWTH,
    FEATURE_GROSS_MARGIN, FEATURE_OPERATING_MARGIN, FEATURE_NET_MARGIN,
    FEATURE_ROE, FEATURE_ROA, FEATURE_ROIC,
    FEATURE_DEBT_TO_EQUITY, FEATURE_CURRENT_RATIO, FEATURE_QUICK_RATIO,
    FEATURE_INTEREST_COVERAGE, FEATURE_ALTMAN_Z,
    FEATURE_OCF_MARGIN, FEATURE_FCF_MARGIN, FEATURE_CASH_CONVERSION,
    FEATURE_EARNINGS_CONSISTENCY, FEATURE_MARGIN_STABILITY,
    FEATURE_CAPITAL_EFFICIENCY, FEATURE_BALANCE_SHEET_QUALITY,
]


@dataclass(frozen=True)
class FundamentalEngineConfig:
    """Runtime settings: feature freshness, decision threshold, and the
    fixed expected-return scale (fundamentals have no natural per-period
    volatility measure the way price ATR does for the Technical Engine,
    so a maximally strong fundamental signal is defined to imply this
    configured expected-return skew)."""

    max_feature_age_seconds: int = 86400  # 24 hours - fundamentals change slowly
    decision_threshold: float = 0.2
    expected_return_scale_pct: float = 10.0
    engine_version: str = "v1"

    @classmethod
    def from_env(cls) -> "FundamentalEngineConfig":
        load_dotenv()
        return cls(
            max_feature_age_seconds=int(
                os.getenv("FUNDAMENTAL_ENGINE_MAX_FEATURE_AGE_SECONDS", "86400")
            ),
            decision_threshold=float(
                os.getenv("FUNDAMENTAL_ENGINE_DECISION_THRESHOLD", "0.2")
            ),
            expected_return_scale_pct=float(
                os.getenv("FUNDAMENTAL_ENGINE_EXPECTED_RETURN_SCALE_PCT", "10.0")
            ),
            engine_version=os.getenv("FUNDAMENTAL_ENGINE_VERSION", "v1"),
        )
