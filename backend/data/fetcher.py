import yfinance as yf
import pandas as pd
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
