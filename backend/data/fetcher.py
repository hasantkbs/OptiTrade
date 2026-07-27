import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def fetch_history(symbol: str, period: str = "1mo") -> Optional[pd.DataFrame]:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            logger.warning(f"No data returned for {symbol}")
            return None
        return hist
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return None


def fetch_info(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        return ticker.info or {}
    except Exception:
        return {}


def fetch_bist100_volume() -> Optional[float]:
    hist = fetch_history("XU100.IS", period="5d")
    if hist is None or hist.empty:
        return None
    return float(hist["Volume"].iloc[-1])


def get_balance_status(symbol: str) -> str:
    info = fetch_info(symbol)
    forward_eps = info.get("forwardEps", None)
    trailing_eps = info.get("trailingEps", None)
    if forward_eps is None or trailing_eps is None:
        return "Nötr"
    return "Pozitif" if forward_eps > trailing_eps else "Negatif"


def fetch_financials(symbol: str) -> Optional[pd.DataFrame]:
    """Annual income statement (multi-year columns, most recent first)."""
    try:
        ticker = yf.Ticker(symbol)
        financials = ticker.financials
        if financials is None or financials.empty:
            logger.warning(f"No financials returned for {symbol}")
            return None
        return financials
    except Exception as e:
        logger.error(f"Error fetching financials for {symbol}: {e}")
        return None


def fetch_balance_sheet(symbol: str) -> Optional[pd.DataFrame]:
    """Annual balance sheet (multi-year columns, most recent first)."""
    try:
        ticker = yf.Ticker(symbol)
        balance_sheet = ticker.balance_sheet
        if balance_sheet is None or balance_sheet.empty:
            logger.warning(f"No balance sheet returned for {symbol}")
            return None
        return balance_sheet
    except Exception as e:
        logger.error(f"Error fetching balance sheet for {symbol}: {e}")
        return None


def fetch_cashflow_statement(symbol: str) -> Optional[pd.DataFrame]:
    """Annual cash flow statement (multi-year columns, most recent first)."""
    try:
        ticker = yf.Ticker(symbol)
        cashflow = ticker.cashflow
        if cashflow is None or cashflow.empty:
            logger.warning(f"No cash flow statement returned for {symbol}")
            return None
        return cashflow
    except Exception as e:
        logger.error(f"Error fetching cash flow statement for {symbol}: {e}")
        return None


def fetch_price_history_range(symbol: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
    """Daily OHLCV history for an arbitrary `[start, end)` date range (as
    opposed to `fetch_history`'s relative `period` window) - used by the
    Continuous Learning system to look up prices as of an arbitrary past
    decision timestamp."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end)
        if hist is None or hist.empty:
            logger.warning(f"No price history returned for {symbol} in range {start}..{end}")
            return None
        return hist
    except Exception as e:
        logger.error(f"Error fetching price history range for {symbol}: {e}")
        return None
