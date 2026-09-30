"""
OptiTrade Paper Trading & Trade Journal Platform — simulated execution.

Pure simulation math (price/commission/latency/market-hours) - no
persistence, no side effects. `fills.py` is the orchestrator that calls
this module and then records the result.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Optional

import pytz

from paper_trading.config import PaperTradingConfig
from paper_trading.exceptions import MarketClosedError
from paper_trading.models import OrderSide, OrderType

logger = logging.getLogger(__name__)


def _is_24_7_symbol(symbol: str) -> bool:
    """Crypto pairs (e.g. `BTC-USD`) trade around the clock; anything
    else (equities, `*.IS` BIST tickers, ...) is subject to market-hours
    validation."""
    return "-" in symbol


class ExecutionEngine:
    def __init__(self, config: Optional[PaperTradingConfig] = None, rng: Optional[random.Random] = None) -> None:
        self.config = config or PaperTradingConfig.from_env()
        self._rng = rng or random.Random()

    # ── Market hours ─────────────────────────────────────────────────────

    def is_market_open(self, symbol: str, now: Optional[datetime] = None) -> bool:
        if _is_24_7_symbol(symbol):
            return True
        now = now or datetime.now(timezone.utc)
        local_time = now.astimezone(pytz.timezone(self.config.market_timezone))
        if local_time.weekday() not in self.config.market_trading_days:
            return False
        return self.config.market_open_hour <= local_time.hour < self.config.market_close_hour

    def validate_market_hours(self, symbol: str, order_type: OrderType, now: Optional[datetime] = None) -> None:
        """Only MARKET orders are rejected outright for a closed market -
        resting orders (LIMIT/STOP/TAKE_PROFIT) are allowed to queue and
        simply won't be evaluated by the scheduler until the market reopens."""
        if order_type == OrderType.MARKET and not self.is_market_open(symbol, now):
            raise MarketClosedError(f"{symbol} market is closed - cannot execute a market order right now")

    # ── Price simulation (slippage + spread) ────────────────────────────

    def simulate_execution_price(self, side: OrderSide, reference_price: float) -> float:
        """Slippage and half the simulated spread always work AGAINST
        the trader - a BUY pays a bit more than the reference price, a
        SELL receives a bit less."""
        sign = 1.0 if side == OrderSide.BUY else -1.0
        adverse_bps = self.config.slippage_bps + (self.config.spread_bps / 2.0)
        return reference_price * (1.0 + sign * adverse_bps / 10_000.0)

    # ── Commission / tax ─────────────────────────────────────────────────

    def compute_commission(self, notional: float) -> float:
        return max(self.config.commission_min, notional * self.config.commission_rate)

    def compute_tax(self, realized_gain: float) -> float:
        """Only realized GAINS are taxed - a realized loss owes no tax."""
        return max(realized_gain, 0.0) * self.config.tax_rate

    # ── Latency ──────────────────────────────────────────────────────────

    def simulate_latency_ms(self) -> int:
        return self._rng.randint(self.config.latency_ms_min, self.config.latency_ms_max)

    # ── Trigger conditions (resting orders) ─────────────────────────────

    def is_triggered(self, order_type: OrderType, side: OrderSide, current_price: float,
                      limit_price: Optional[float], stop_price: Optional[float]) -> bool:
        if order_type == OrderType.LIMIT:
            return current_price <= limit_price if side == OrderSide.BUY else current_price >= limit_price
        if order_type == OrderType.STOP:
            return current_price >= stop_price if side == OrderSide.BUY else current_price <= stop_price
        if order_type == OrderType.TAKE_PROFIT:
            return current_price >= stop_price if side == OrderSide.SELL else current_price <= stop_price
        return False
