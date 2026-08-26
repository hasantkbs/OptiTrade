"""
OptiTrade Fundamental Engine — Feature Store adapter.

The ONLY module in this engine allowed to fetch raw fundamental data.
Every analyzer module (valuation.py, growth.py, profitability.py,
financial_health.py, cashflow.py, quality.py) consumes only the
`Dict[str, float]` this returns — never `data.fetcher`/yfinance directly.

Reuses existing data-access logic rather than duplicating it:
`data/fetcher.fetch_info` (unchanged, already used by
`core/scoring.py`'s `get_balance_status` for the exact same underlying
yfinance `.info` dict) plus three new, purely additive wrapper functions
this task added to `data/fetcher.py`
(`fetch_financials`/`fetch_balance_sheet`/`fetch_cashflow_statement`) for
the multi-year statement data no existing module previously exposed.

Feature Store is checked first for each feature name; only missing or
stale (older than `FundamentalEngineConfig.max_feature_age_seconds` —
24 hours by default, since fundamentals change far more slowly than
technical indicators) features trigger a fresh computation, written back
to the Feature Store.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.structured_logging import STATUS_SUCCESS, log_event
from data.fetcher import fetch_balance_sheet, fetch_cashflow_statement, fetch_financials, fetch_info
from engines.fundamental.config import (
    ALL_FEATURE_NAMES,
    FEATURE_ALTMAN_Z,
    FEATURE_BALANCE_SHEET_QUALITY,
    FEATURE_CAPITAL_EFFICIENCY,
    FEATURE_CASH_CONVERSION,
    FEATURE_CURRENT_RATIO,
    FEATURE_DEBT_TO_EQUITY,
    FEATURE_EARNINGS_CONSISTENCY,
    FEATURE_EPS_GROWTH,
    FEATURE_EV_TO_EBITDA,
    FEATURE_FCF_GROWTH,
    FEATURE_FCF_MARGIN,
    FEATURE_FORWARD_PE,
    FEATURE_GROSS_MARGIN,
    FEATURE_INTEREST_COVERAGE,
    FEATURE_MARGIN_STABILITY,
    FEATURE_NET_MARGIN,
    FEATURE_OCF_MARGIN,
    FEATURE_OPERATING_INCOME_GROWTH,
    FEATURE_OPERATING_MARGIN,
    FEATURE_PE,
    FEATURE_PEG,
    FEATURE_PRICE_TO_BOOK,
    FEATURE_PRICE_TO_SALES,
    FEATURE_QUICK_RATIO,
    FEATURE_REVENUE_GROWTH,
    FEATURE_ROA,
    FEATURE_ROE,
    FEATURE_ROIC,
    FundamentalEngineConfig,
)
from feature_store.models import FeatureValue
from feature_store.resolution import FeatureResolution, resolve_features
from feature_store.service import FeatureStoreService, get_default_feature_store_service

logger = logging.getLogger(__name__)


def _row(df: Optional[pd.DataFrame], label: str) -> Optional[pd.Series]:
    if df is None or label not in df.index:
        return None
    return df.loc[label]


def _latest(series: Optional[pd.Series]) -> Optional[float]:
    if series is None:
        return None
    for value in series:
        if pd.notna(value):
            return float(value)
    return None


def _yoy_growth_pct(series: Optional[pd.Series]) -> Optional[float]:
    """`series` is ordered most-recent-first (yfinance statement column
    order). Returns percent growth from the second-most-recent to the
    most recent non-NaN value, or None with fewer than 2 usable years."""
    if series is None:
        return None
    valid = [float(v) for v in series if pd.notna(v)]
    if len(valid) < 2 or valid[1] == 0:
        return None
    return (valid[0] - valid[1]) / abs(valid[1]) * 100


def _paired_years(a: Optional[pd.Series], b: Optional[pd.Series]) -> List[Tuple[float, float]]:
    """Years where both series have a non-NaN value, in original column order."""
    if a is None or b is None:
        return []
    pairs = []
    for col in a.index:
        va, vb = a.get(col), b.get(col)
        if pd.notna(va) and pd.notna(vb):
            pairs.append((float(va), float(vb)))
    return pairs


class FundamentalFeatureAdapter:
    """Bridges the Feature Store with the underlying (reused)
    fundamental-data access. Constructed lazily by
    `engine.py::FundamentalEngine` so merely importing/registering the
    engine never opens a database connection."""

    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        config: Optional[FundamentalEngineConfig] = None,
    ) -> None:
        self.feature_store = feature_store or get_default_feature_store_service()
        self.config = config or FundamentalEngineConfig.from_env()

    def get_features(self, symbol: str) -> FeatureResolution:
        resolution = resolve_features(
            self.feature_store, symbol, ALL_FEATURE_NAMES, self.config.max_feature_age_seconds, self._compute_all,
        )
        log_event(
            logger, component="fundamental_engine", module="engines.fundamental.feature_adapter",
            operation="get_features", status=STATUS_SUCCESS, symbol=symbol,
            features_from_cache=len(resolution.from_cache),
            features_computed_fresh=len(resolution.computed_fresh),
        )
        return resolution

    def _compute_all(self, symbol: str) -> Dict[str, float]:
        started_at = time.perf_counter()
        info = fetch_info(symbol)
        financials = fetch_financials(symbol)
        balance_sheet = fetch_balance_sheet(symbol)
        cashflow = fetch_cashflow_statement(symbol)

        values: Dict[str, float] = {}
        values.update(self._valuation_from_info(info))
        values.update(self._growth(info, financials, cashflow))
        values.update(self._profitability(info, financials, balance_sheet))
        values.update(self._financial_health(info, financials, balance_sheet))
        values.update(self._cashflow_metrics(financials, cashflow))
        values.update(self._quality(financials, balance_sheet))

        for name, value in values.items():
            if value is not None and not (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
                self.feature_store.write_feature(FeatureValue(symbol=symbol, feature_name=name, value=value))

        log_event(
            logger, component="fundamental_engine", module="engines.fundamental.feature_adapter",
            operation="compute_all", status=STATUS_SUCCESS, symbol=symbol,
            features_computed=len(values),
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return {k: v for k, v in values.items() if v is not None}

    @staticmethod
    def _valuation_from_info(info: dict) -> Dict[str, Optional[float]]:
        return {
            FEATURE_PE: info.get("trailingPE"),
            FEATURE_FORWARD_PE: info.get("forwardPE"),
            FEATURE_PEG: info.get("pegRatio"),
            FEATURE_PRICE_TO_SALES: info.get("priceToSalesTrailing12Months"),
            FEATURE_PRICE_TO_BOOK: info.get("priceToBook"),
            FEATURE_EV_TO_EBITDA: info.get("enterpriseToEbitda"),
        }

    @staticmethod
    def _growth(
        info: dict, financials: Optional[pd.DataFrame], cashflow: Optional[pd.DataFrame]
    ) -> Dict[str, Optional[float]]:
        revenue_growth = info.get("revenueGrowth")
        eps_growth = info.get("earningsGrowth")
        return {
            FEATURE_REVENUE_GROWTH: revenue_growth * 100 if revenue_growth is not None else None,
            FEATURE_EPS_GROWTH: eps_growth * 100 if eps_growth is not None else None,
            FEATURE_OPERATING_INCOME_GROWTH: _yoy_growth_pct(_row(financials, "Operating Income")),
            FEATURE_FCF_GROWTH: _yoy_growth_pct(_row(cashflow, "Free Cash Flow")),
        }

    @staticmethod
    def _profitability(
        info: dict, financials: Optional[pd.DataFrame], balance_sheet: Optional[pd.DataFrame]
    ) -> Dict[str, Optional[float]]:
        gross_margin = info.get("grossMargins")
        operating_margin = info.get("operatingMargins")
        net_margin = info.get("profitMargins")
        roe = info.get("returnOnEquity")
        roa = info.get("returnOnAssets")

        ebit = _latest(_row(financials, "EBIT"))
        invested_capital = _latest(_row(balance_sheet, "Invested Capital"))
        roic = (ebit / invested_capital * 100) if ebit is not None and invested_capital else None

        return {
            FEATURE_GROSS_MARGIN: gross_margin * 100 if gross_margin is not None else None,
            FEATURE_OPERATING_MARGIN: operating_margin * 100 if operating_margin is not None else None,
            FEATURE_NET_MARGIN: net_margin * 100 if net_margin is not None else None,
            FEATURE_ROE: roe * 100 if roe is not None else None,
            FEATURE_ROA: roa * 100 if roa is not None else None,
            FEATURE_ROIC: roic,
        }

    @staticmethod
    def _financial_health(
        info: dict, financials: Optional[pd.DataFrame], balance_sheet: Optional[pd.DataFrame]
    ) -> Dict[str, Optional[float]]:
        ebit = _latest(_row(financials, "EBIT"))
        interest_expense = _latest(_row(financials, "Interest Expense"))
        interest_coverage = (
            ebit / abs(interest_expense) if ebit is not None and interest_expense else None
        )

        working_capital = _latest(_row(balance_sheet, "Working Capital"))
        retained_earnings = _latest(_row(balance_sheet, "Retained Earnings"))
        total_assets = _latest(_row(balance_sheet, "Total Assets"))
        total_liabilities = _latest(_row(balance_sheet, "Total Liabilities Net Minority Interest"))
        revenue = _latest(_row(financials, "Total Revenue"))
        market_cap = info.get("marketCap")

        altman_z = None
        if all(
            v is not None
            for v in (working_capital, retained_earnings, ebit, total_assets, total_liabilities, revenue, market_cap)
        ) and total_assets and total_liabilities:
            altman_z = (
                1.2 * (working_capital / total_assets)
                + 1.4 * (retained_earnings / total_assets)
                + 3.3 * (ebit / total_assets)
                + 0.6 * (market_cap / total_liabilities)
                + 1.0 * (revenue / total_assets)
            )

        return {
            FEATURE_DEBT_TO_EQUITY: info.get("debtToEquity"),
            FEATURE_CURRENT_RATIO: info.get("currentRatio"),
            FEATURE_QUICK_RATIO: info.get("quickRatio"),
            FEATURE_INTEREST_COVERAGE: interest_coverage,
            FEATURE_ALTMAN_Z: altman_z,
        }

    @staticmethod
    def _cashflow_metrics(
        financials: Optional[pd.DataFrame], cashflow: Optional[pd.DataFrame]
    ) -> Dict[str, Optional[float]]:
        revenue = _latest(_row(financials, "Total Revenue"))
        net_income = _latest(_row(financials, "Net Income"))
        ocf = _latest(_row(cashflow, "Operating Cash Flow"))
        fcf = _latest(_row(cashflow, "Free Cash Flow"))

        return {
            FEATURE_OCF_MARGIN: (ocf / revenue * 100) if ocf is not None and revenue else None,
            FEATURE_FCF_MARGIN: (fcf / revenue * 100) if fcf is not None and revenue else None,
            FEATURE_CASH_CONVERSION: (ocf / net_income) if ocf is not None and net_income else None,
        }

    @staticmethod
    def _quality(
        financials: Optional[pd.DataFrame], balance_sheet: Optional[pd.DataFrame]
    ) -> Dict[str, Optional[float]]:
        net_income_series = _row(financials, "Net Income")
        revenue_series = _row(financials, "Total Revenue")

        earnings_consistency = None
        if net_income_series is not None:
            valid = [float(v) for v in net_income_series if pd.notna(v)]
            if valid:
                earnings_consistency = sum(1 for v in valid if v > 0) / len(valid)

        margin_stability = None
        pairs = _paired_years(net_income_series, revenue_series)
        margins = [ni / rev * 100 for ni, rev in pairs if rev != 0]
        if len(margins) >= 2:
            mean_margin = float(np.mean(margins))
            std_margin = float(np.std(margins))
            if mean_margin != 0:
                coefficient_of_variation = abs(std_margin / mean_margin)
                margin_stability = max(0.0, min(1.0, 1 - coefficient_of_variation))

        revenue = _latest(revenue_series)
        total_assets = _latest(_row(balance_sheet, "Total Assets"))
        capital_efficiency = (revenue / total_assets * 100) if revenue is not None and total_assets else None

        total_debt = _latest(_row(balance_sheet, "Total Debt"))
        balance_sheet_quality = None
        if total_debt is not None and total_assets:
            balance_sheet_quality = max(0.0, min(1.0, 1 - total_debt / total_assets))

        return {
            FEATURE_EARNINGS_CONSISTENCY: earnings_consistency,
            FEATURE_MARGIN_STABILITY: margin_stability,
            FEATURE_CAPITAL_EFFICIENCY: capital_efficiency,
            FEATURE_BALANCE_SHEET_QUALITY: balance_sheet_quality,
        }
