"""OptiTrade Paper Trading & Trade Journal Platform — order lifecycle."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from paper_trading.exceptions import AccountNotFoundError, InvalidOrderError, OrderNotFoundError, OrderNotOpenError
from paper_trading.execution import ExecutionEngine
from paper_trading.models import Order, OrderSide, OrderStatus, OrderType
from paper_trading.repository import PaperTradingRepository

logger = logging.getLogger(__name__)
_MODULE = "paper_trading.orders"
_COMPONENT = "paper_trading"


class OrderService:
    def __init__(self, repository: PaperTradingRepository, execution: Optional[ExecutionEngine] = None) -> None:
        self._repository = repository
        self._execution = execution or ExecutionEngine()

    def create_order(
        self, account_id: int, symbol: str, side: OrderSide, order_type: OrderType, quantity: float,
        limit_price: Optional[float] = None, stop_price: Optional[float] = None, notes: str = "",
        now: Optional[datetime] = None,
    ) -> Order:
        started_at = time.perf_counter()
        if self._repository.get_account(account_id) is None:
            raise AccountNotFoundError(f"paper trading account {account_id} not found")

        try:
            order = Order(
                account_id=account_id, symbol=symbol, side=side, order_type=order_type, quantity=quantity,
                limit_price=limit_price, stop_price=stop_price, notes=notes,
            )
        except Exception as exc:
            self._log_error("create_order", exc, started_at, account_id=account_id, symbol=symbol)
            raise InvalidOrderError(str(exc)) from exc

        self._execution.validate_market_hours(order.symbol, order.order_type, now=now)

        order_id = self._repository.save_order(order)
        self._log_success("create_order", started_at, account_id=account_id, order_id=order_id)
        return self._repository.get_order(order_id)

    def get_order(self, order_id: int) -> Order:
        order = self._repository.get_order(order_id)
        if order is None:
            raise OrderNotFoundError(f"order {order_id} not found")
        return order

    def list_orders(self, account_id: int, status: Optional[OrderStatus] = None) -> List[Order]:
        return self._repository.list_orders(account_id, status=status)

    def cancel_order(self, order_id: int) -> Order:
        started_at = time.perf_counter()
        order = self.get_order(order_id)
        if not order.is_open:
            raise OrderNotOpenError(f"order {order_id} is {order.status.value!r} and cannot be cancelled")

        now = datetime.now(timezone.utc)
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = now
        order.updated_at = now
        self._repository.update_order(order)
        self._log_success("cancel_order", started_at, order_id=order_id)
        return self._repository.get_order(order_id)

    def modify_order(
        self, order_id: int, quantity: Optional[float] = None, limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        started_at = time.perf_counter()
        order = self.get_order(order_id)
        if not order.is_open:
            raise OrderNotOpenError(f"order {order_id} is {order.status.value!r} and cannot be modified")
        if order.filled_quantity > 0:
            raise OrderNotOpenError(f"order {order_id} already has partial fills and cannot be modified")

        try:
            candidate = Order(
                id=order.id, account_id=order.account_id, symbol=order.symbol, side=order.side,
                order_type=order.order_type, quantity=quantity if quantity is not None else order.quantity,
                limit_price=limit_price if limit_price is not None else order.limit_price,
                stop_price=stop_price if stop_price is not None else order.stop_price,
                status=order.status, filled_quantity=order.filled_quantity,
                average_fill_price=order.average_fill_price, commission_paid=order.commission_paid,
                tax_paid=order.tax_paid, created_at=order.created_at, updated_at=datetime.now(timezone.utc),
                notes=order.notes,
            )
        except Exception as exc:
            raise InvalidOrderError(str(exc)) from exc

        self._repository.update_order(candidate)
        self._log_success("modify_order", started_at, order_id=order_id)
        return self._repository.get_order(order_id)

    def _log_success(self, operation: str, started_at: float, **extra) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, **extra,
        )

    def _log_error(self, operation: str, exc: Exception, started_at: float, **extra) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_ERROR,
            error_type=type(exc).__name__, execution_time_ms=(time.perf_counter() - started_at) * 1000,
            level=logging.ERROR, **extra,
        )
