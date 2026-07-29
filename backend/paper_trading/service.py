"""
OptiTrade Paper Trading & Trade Journal Platform — top-level facade.

Composes every sub-service into the single entry point FastAPI
endpoints (and any other caller) should use: placing an order runs
execution immediately for MARKET orders (or leaves LIMIT/STOP/
TAKE_PROFIT resting for `scheduler.py` to pick up later), synchronizes
the real Portfolio ledger/Watchlist/Alerts, and journals the decision
context - all in one call.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from paper_trading.analytics import AnalyticsService
from paper_trading.exceptions import AccountNotFoundError
from paper_trading.execution import ExecutionEngine
from paper_trading.fills import FillService
from paper_trading.journal import JournalService
from paper_trading.models import (
    AnalyticsSummary,
    ClosedTrade,
    EquityPoint,
    MonthlyPerformance,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    ReportPeriod,
    TradeJournalEntry,
    TradeReport,
)
from paper_trading.orders import OrderService
from paper_trading.portfolio_sync import PortfolioSyncService
from paper_trading.positions import PositionService
from paper_trading.repository import PaperTradingRepository
from paper_trading.reports import ReportService
from portfolio.models import PositionAnalytics
from portfolio.prices import PriceService

logger = logging.getLogger(__name__)
_MODULE = "paper_trading.service"
_COMPONENT = "paper_trading"


class PaperTradingService:
    def __init__(
        self,
        repository: PaperTradingRepository,
        portfolio_sync: PortfolioSyncService,
        position_service: PositionService,
        journal_service: JournalService,
        execution: Optional[ExecutionEngine] = None,
        order_service: Optional[OrderService] = None,
        fill_service: Optional[FillService] = None,
        analytics_service: Optional[AnalyticsService] = None,
        report_service: Optional[ReportService] = None,
        price_service: Optional[PriceService] = None,
    ) -> None:
        self._repository = repository
        self._portfolio_sync = portfolio_sync
        self._position_service = position_service
        self._journal_service = journal_service
        self._execution = execution or ExecutionEngine()
        self._order_service = order_service or OrderService(repository, self._execution)
        self._fill_service = fill_service or FillService(repository, self._execution)
        self._analytics_service = analytics_service or AnalyticsService(repository)
        self._report_service = report_service or ReportService(self._analytics_service)
        self._price_service = price_service or PriceService()

    # ── Accounts ─────────────────────────────────────────────────────────

    def ensure_account(
        self, user_id: int, owner_email: str, name: str = "Paper Trading Account",
        starting_balance: float = 100_000.0,
    ) -> PaperAccount:
        return self._portfolio_sync.ensure_account(user_id, owner_email, name=name, starting_balance=starting_balance)

    def get_account(self, account_id: int) -> PaperAccount:
        account = self._repository.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(f"paper trading account {account_id} not found")
        return account

    def list_accounts(self, user_id: int) -> List[PaperAccount]:
        return self._repository.list_accounts(user_id)

    # ── Orders ───────────────────────────────────────────────────────────

    def place_order(
        self,
        account_id: int,
        owner_email: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        notes: str = "",
        now: Optional[datetime] = None,
    ) -> Order:
        started_at = time.perf_counter()
        order = self._order_service.create_order(
            account_id, symbol, side, order_type, quantity, limit_price=limit_price, stop_price=stop_price,
            notes=notes, now=now,
        )
        account = self.get_account(account_id)

        if order.order_type == OrderType.MARKET:
            order = self._execute_market_order(account, order, now=now)
        else:
            self._portfolio_sync.sync_stop_take_profit_alert(account, owner_email, order)

        self._portfolio_sync.sync_watchlist(account, owner_email, order.symbol)
        self._journal_service.record_trade_decision(order)

        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="place_order", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, account_id=account_id, order_id=order.id,
        )
        return order

    def _execute_market_order(self, account: PaperAccount, order: Order, now: Optional[datetime]) -> Order:
        reference_price = self._price_service.get_current_price(order.symbol)
        average_cost = (
            self._portfolio_sync.get_average_cost(account, order.symbol) if order.side == OrderSide.SELL else None
        )
        fill = self._fill_service.record_fill(order, reference_price=reference_price, average_cost=average_cost, now=now)
        self._portfolio_sync.sync_fill(account, fill)
        return self._order_service.get_order(order.id)

    def cancel_order(self, order_id: int) -> Order:
        return self._order_service.cancel_order(order_id)

    def modify_order(
        self, order_id: int, quantity: Optional[float] = None, limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        return self._order_service.modify_order(order_id, quantity=quantity, limit_price=limit_price, stop_price=stop_price)

    def get_order(self, order_id: int) -> Order:
        return self._order_service.get_order(order_id)

    def list_orders(self, account_id: int, status: Optional[OrderStatus] = None) -> List[Order]:
        return self._order_service.list_orders(account_id, status=status)

    # ── Positions ────────────────────────────────────────────────────────

    def get_positions(self, account_id: int) -> List[PositionAnalytics]:
        return self._position_service.get_positions(self.get_account(account_id))

    def get_cash_balance(self, account_id: int) -> float:
        return self._position_service.get_cash_balance(self.get_account(account_id))

    def get_total_value(self, account_id: int) -> float:
        return self._position_service.get_total_value(self.get_account(account_id))

    # ── Trade journal ────────────────────────────────────────────────────

    def get_journal_entry(self, entry_id: int) -> TradeJournalEntry:
        return self._journal_service.get_entry(entry_id)

    def get_journal_entry_by_order(self, order_id: int) -> Optional[TradeJournalEntry]:
        return self._journal_service.get_entry_by_order(order_id)

    def list_journal_entries(self, account_id: int) -> List[TradeJournalEntry]:
        return self._journal_service.list_entries(account_id)

    def update_journal_notes(self, entry_id: int, notes: str) -> TradeJournalEntry:
        return self._journal_service.update_notes(entry_id, notes)

    def add_journal_tags(self, entry_id: int, tags: List[str]) -> TradeJournalEntry:
        return self._journal_service.add_tags(entry_id, tags)

    def add_journal_screenshot(self, entry_id: int, url: str, caption: str = ""):
        return self._journal_service.add_screenshot(entry_id, url, caption=caption)

    # ── Analytics / reports ──────────────────────────────────────────────

    def get_analytics_summary(self, account_id: int, symbol: Optional[str] = None) -> AnalyticsSummary:
        return self._analytics_service.get_summary(self.get_account(account_id), symbol=symbol)

    def get_closed_trades(self, account_id: int, symbol: Optional[str] = None) -> List[ClosedTrade]:
        return self._analytics_service.get_closed_trades(self.get_account(account_id), symbol=symbol)

    def get_equity_curve(self, account_id: int) -> List[EquityPoint]:
        return self._analytics_service.get_equity_curve(self.get_account(account_id))

    def get_monthly_performance(self, account_id: int) -> List[MonthlyPerformance]:
        return self._analytics_service.get_monthly_performance(self.get_account(account_id))

    def generate_report(
        self, account_id: int, period: ReportPeriod, reference: Optional[datetime] = None,
    ) -> TradeReport:
        return self._report_service.generate(self.get_account(account_id), period, reference=reference)
