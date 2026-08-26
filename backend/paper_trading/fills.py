"""
OptiTrade Paper Trading & Trade Journal Platform — fill recording.

Applies simulated slippage/spread/commission/tax to (part of) an order
and persists the result. Deliberately does NOT touch the real Portfolio
Platform ledger itself - `portfolio_sync.py` does that, given the `Fill`
this module returns, keeping the two concerns independently testable.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from paper_trading.exceptions import OrderNotOpenError
from paper_trading.execution import ExecutionEngine
from paper_trading.models import Fill, Order, OrderSide, OrderStatus
from paper_trading.repository import PaperTradingRepository

logger = logging.getLogger(__name__)
_MODULE = "paper_trading.fills"
_COMPONENT = "paper_trading"


class FillService:
    def __init__(self, repository: PaperTradingRepository, execution: Optional[ExecutionEngine] = None) -> None:
        self._repository = repository
        self._execution = execution or ExecutionEngine()

    def record_fill(
        self, order: Order, reference_price: float, quantity: Optional[float] = None,
        average_cost: Optional[float] = None, now: Optional[datetime] = None,
    ) -> Fill:
        """Executes (part of) `order` against `reference_price`.
        `quantity` defaults to the order's full remaining quantity (a
        full fill); passing a smaller amount simulates a partial fill -
        the order's status becomes PARTIALLY_FILLED until subsequent
        calls exhaust the remaining quantity."""
        started_at = time.perf_counter()
        if not order.is_open:
            raise OrderNotOpenError(f"order {order.id} is {order.status.value!r} and cannot be filled")

        now = now or datetime.now(timezone.utc)
        fill_quantity = min(quantity if quantity is not None else order.remaining_quantity, order.remaining_quantity)

        execution_price = self._execution.simulate_execution_price(order.side, reference_price)
        notional = execution_price * fill_quantity
        commission = self._execution.compute_commission(notional)
        tax = 0.0
        if order.side == OrderSide.SELL and average_cost is not None:
            realized_gain = (execution_price - average_cost) * fill_quantity
            tax = self._execution.compute_tax(realized_gain)

        fill = Fill(
            order_id=order.id, account_id=order.account_id, symbol=order.symbol, side=order.side,
            quantity=fill_quantity, price=execution_price, slippage=execution_price - reference_price,
            commission=commission, tax=tax, executed_at=now,
        )
        fill.id = self._repository.save_fill(fill)

        previous_notional = (order.average_fill_price or 0.0) * order.filled_quantity
        new_filled_quantity = order.filled_quantity + fill_quantity
        order.average_fill_price = (previous_notional + execution_price * fill_quantity) / new_filled_quantity
        order.filled_quantity = new_filled_quantity
        order.commission_paid += commission
        order.tax_paid += tax
        order.status = OrderStatus.FILLED if order.remaining_quantity <= 1e-9 else OrderStatus.PARTIALLY_FILLED
        order.updated_at = now
        self._repository.update_order(order)

        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="record_fill", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, order_id=order.id, fill_id=fill.id,
            quantity=fill_quantity, price=execution_price,
        )
        return fill
