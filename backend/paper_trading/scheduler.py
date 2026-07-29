"""
OptiTrade Paper Trading & Trade Journal Platform — pending order scheduler.

Scans every open (PENDING/PARTIALLY_FILLED) LIMIT/STOP/TAKE_PROFIT
order, fetches the current price once per distinct symbol, and executes
any order whose trigger condition is now met. MARKET orders are never
scanned here - they execute immediately at placement time.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from paper_trading.exceptions import PaperTradingError
from paper_trading.execution import ExecutionEngine
from paper_trading.fills import FillService
from paper_trading.models import Fill, Order, OrderSide, OrderType
from paper_trading.portfolio_sync import PortfolioSyncService
from paper_trading.repository import PaperTradingRepository
from portfolio.prices import PriceService

logger = logging.getLogger(__name__)
_MODULE = "paper_trading.scheduler"
_COMPONENT = "paper_trading"

_RESTING_ORDER_TYPES = (OrderType.LIMIT, OrderType.STOP, OrderType.TAKE_PROFIT)


class PaperTradingScheduler:
    def __init__(
        self,
        repository: PaperTradingRepository,
        portfolio_sync: PortfolioSyncService,
        execution: Optional[ExecutionEngine] = None,
        fill_service: Optional[FillService] = None,
        price_service: Optional[PriceService] = None,
    ) -> None:
        self._repository = repository
        self._portfolio_sync = portfolio_sync
        self._execution = execution or ExecutionEngine()
        self._fill_service = fill_service or FillService(repository, self._execution)
        self._price_service = price_service or PriceService()

    def scan_pending_orders(self, now: Optional[datetime] = None) -> List[Fill]:
        started_at = time.perf_counter()
        resting_orders = [
            order for order in self._repository.list_open_orders() if order.order_type in _RESTING_ORDER_TYPES
        ]
        if not resting_orders:
            return []

        prices = self._fetch_prices({order.symbol for order in resting_orders})
        executed_fills: List[Fill] = []
        for order in resting_orders:
            price = prices.get(order.symbol)
            if price is None:
                continue
            if not self._execution.is_triggered(order.order_type, order.side, price, order.limit_price, order.stop_price):
                continue
            fill = self._execute_triggered_order(order, price, now=now)
            if fill is not None:
                executed_fills.append(fill)

        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="scan_pending_orders", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, scanned=len(resting_orders),
            executed=len(executed_fills),
        )
        return executed_fills

    def _fetch_prices(self, symbols: set) -> Dict[str, float]:
        prices: Dict[str, float] = {}
        for symbol in symbols:
            try:
                prices[symbol] = self._price_service.get_current_price(symbol)
            except Exception as exc:
                log_event(
                    logger, component=_COMPONENT, module=_MODULE, operation="fetch_price", status=STATUS_ERROR,
                    error_type=type(exc).__name__, symbol=symbol, level=logging.WARNING,
                )
        return prices

    def _execute_triggered_order(self, order: Order, price: float, now: Optional[datetime]) -> Optional[Fill]:
        try:
            account = self._repository.get_account(order.account_id)
            average_cost = (
                self._portfolio_sync.get_average_cost(account, order.symbol) if order.side == OrderSide.SELL else None
            )
            fill = self._fill_service.record_fill(order, reference_price=price, average_cost=average_cost, now=now)
            self._portfolio_sync.sync_fill(account, fill)
            return fill
        except PaperTradingError as exc:
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="execute_triggered_order", status=STATUS_ERROR,
                error_type=type(exc).__name__, order_id=order.id, level=logging.WARNING,
            )
            return None
