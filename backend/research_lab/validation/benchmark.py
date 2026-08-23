"""
OptiTrade Research Lab — Decision Engine validation: buy-and-hold benchmark.

Real market data only (`data.fetcher.fetch_price_history_range`, the
same fetcher `ml_training.labels.generator`/`learning.evaluator` already
use for realized-outcome pricing) - never a fabricated or assumed
benchmark return. A fetch failure or an empty/too-short history degrades
to `None` (missing-data behavior), never raises and never fabricates a
substitute value.

The benchmark Sharpe ratio is computed over DAILY returns (the natural
cadence of a buy-and-hold position), while a `ValidationReport`'s own
`sharpe_ratio` is computed over irregularly-horizoned trade returns
(see `core.performance_metrics`'s own docstring: deliberately not
annualized, since trade horizons vary). The two Sharpe values are
therefore on different time bases and not directly comparable without
an annualization assumption this module deliberately does not
introduce - see `ValidationReport`'s docstring and this project's
final validation report for that limitation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional, Tuple

from core.performance_metrics import sharpe_ratio
from data.fetcher import fetch_price_history_range

PriceFetcher = Callable[[str, datetime, datetime], "object"]


def compute_benchmark(
    symbol: str, window_start: datetime, window_end: datetime,
    price_fetcher: Optional[PriceFetcher] = None, risk_free_rate: float = 0.0,
) -> Optional[Tuple[float, float]]:
    """`(total_return_pct, sharpe_ratio)` for a buy-and-hold position
    over `[window_start, window_end]`, or `None` if real price history
    isn't available for that window."""
    price_fetcher = price_fetcher or fetch_price_history_range
    history = price_fetcher(symbol, window_start, window_end)
    if history is None or history.empty or len(history) < 2:
        return None

    closes = history["Close"]
    total_return_pct = float((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100.0)
    daily_returns_pct = (closes.pct_change().dropna() * 100.0).tolist()
    return total_return_pct, sharpe_ratio(daily_returns_pct, risk_free_rate)
