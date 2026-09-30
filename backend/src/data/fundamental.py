"""
OptiTrade — Fundamental Data Fetcher
======================================
Provides FundamentalData snapshots from the registered MarketDataProvider.
Callers receive a clean typed dataclass; provider details stay hidden.

All fields are Optional[float].  NaN, None, and "N/A" values from the
provider are normalised to None so business logic never needs to guard
against unexpected sentinel values.
"""
import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FundamentalData:
    """
    Fundamental financial metrics for a single equity symbol.

    All ratio/margin fields use their natural units:
      - ROE, ROA, profit_margin, operating_margin, revenue_growth,
        earnings_growth, dividend_yield, payout_ratio are decimals
        (e.g. 0.20 means 20%)
      - pe_ratio, pb_ratio, ps_ratio, ev_ebitda, debt_to_equity,
        current_ratio, beta are plain multiples / ratios
      - market_cap, eps_ttm use the currency of the symbol's exchange
    """
    symbol: str

    # Valuation
    pe_ratio:         Optional[float] = None
    forward_pe:       Optional[float] = None
    pb_ratio:         Optional[float] = None
    ps_ratio:         Optional[float] = None
    ev_ebitda:        Optional[float] = None

    # Profitability
    roe:              Optional[float] = None   # Return on equity
    roa:              Optional[float] = None   # Return on assets
    profit_margin:    Optional[float] = None   # Net profit margin
    operating_margin: Optional[float] = None

    # Growth
    revenue_growth:   Optional[float] = None   # YoY revenue growth
    earnings_growth:  Optional[float] = None   # YoY earnings growth

    # Financial health
    debt_to_equity:   Optional[float] = None
    current_ratio:    Optional[float] = None

    # Dividends
    dividend_yield:   Optional[float] = None   # e.g. 0.025 = 2.5%
    payout_ratio:     Optional[float] = None

    # Market / other
    market_cap:       Optional[float] = None
    beta:             Optional[float] = None
    eps_ttm:          Optional[float] = None


def fetch_fundamental_data(symbol: str) -> Optional[FundamentalData]:
    """
    Fetch fundamental data for `symbol` via the registered provider.

    Returns None when:
      - The provider returns an empty dict
      - The symbol is a cryptocurrency (quoteType == CRYPTOCURRENCY)
      - Any exception occurs during fetching

    Fundamental fields that are missing, None, or NaN in the raw provider
    response are normalised to None in the returned FundamentalData.
    """
    try:
        from data.fetcher import fetch_info
        info = fetch_info(symbol)
        if not info:
            return None
        if info.get("quoteType") == "CRYPTOCURRENCY":
            return None

        def _f(key: str) -> Optional[float]:
            v = info.get(key)
            if v is None:
                return None
            try:
                f = float(v)
                return None if math.isnan(f) or math.isinf(f) else f
            except (TypeError, ValueError):
                return None

        return FundamentalData(
            symbol           = symbol,
            pe_ratio         = _f("trailingPE"),
            forward_pe       = _f("forwardPE"),
            pb_ratio         = _f("priceToBook"),
            ps_ratio         = _f("priceToSalesTrailingTwelveMonths"),
            ev_ebitda        = _f("enterpriseToEbitda"),
            roe              = _f("returnOnEquity"),
            roa              = _f("returnOnAssets"),
            profit_margin    = _f("profitMargins"),
            operating_margin = _f("operatingMargins"),
            revenue_growth   = _f("revenueGrowth"),
            earnings_growth  = _f("earningsGrowth"),
            debt_to_equity   = _f("debtToEquity"),
            current_ratio    = _f("currentRatio"),
            dividend_yield   = _f("dividendYield"),
            payout_ratio     = _f("payoutRatio"),
            market_cap       = _f("marketCap"),
            beta             = _f("beta"),
            eps_ttm          = _f("trailingEps"),
        )
    except Exception as exc:
        logger.debug("fetch_fundamental_data failed for %s: %s", symbol, exc)
        return None
