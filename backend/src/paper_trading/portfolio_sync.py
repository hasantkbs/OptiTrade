"""
OptiTrade Paper Trading & Trade Journal Platform — portfolio sync.

Automatic synchronization with the Portfolio Platform (every paper
account is backed by a real `portfolio.PortfolioService` ledger; every
fill is replayed into it as a real `buy`/`sell` transaction), Watchlists
(traded symbols are automatically tracked), and Alerts (STOP/TAKE_PROFIT
orders get a mirrored price Alert so the existing Alert Platform also
notifies the user). Decision Engine/Continuous Learning sync happens
implicitly: every decision this platform uses comes from
`pipeline.PipelineService.run()`, which already records into Continuous
Learning itself (see `journal.py`).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from paper_trading.models import Fill, Order, OrderSide, OrderType, PaperAccount
from paper_trading.repository import PaperTradingRepository
from portfolio.models import Transaction
from portfolio.service import PortfolioService
from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.repository import WatchlistRepository
from watchlist.watchlist_service import WatchlistService

logger = logging.getLogger(__name__)
_MODULE = "paper_trading.portfolio_sync"
_COMPONENT = "paper_trading"

_PAPER_WATCHLIST_NAME = "Paper Trading"
_DEFAULT_STARTING_BALANCE = 100_000.0


class PortfolioSyncService:
    def __init__(
        self,
        repository: PaperTradingRepository,
        portfolio_service: PortfolioService,
        watchlist_service: Optional[WatchlistService] = None,
        watchlist_repository: Optional[WatchlistRepository] = None,
    ) -> None:
        self._repository = repository
        self._portfolio_service = portfolio_service
        self._watchlist_service = watchlist_service
        self._watchlist_repository = watchlist_repository

    def ensure_account(
        self, user_id: int, owner_email: str, name: str = "Paper Trading Account",
        starting_balance: float = _DEFAULT_STARTING_BALANCE,
    ) -> PaperAccount:
        """Returns the user's existing paper account if one exists,
        otherwise creates a brand-new real `Portfolio` (via
        `PortfolioService`), funds it with `starting_balance`, and
        records the link in this platform's own `paper_trading_accounts`
        table."""
        existing = self._repository.list_accounts(user_id)
        if existing:
            return existing[0]

        started_at = time.perf_counter()
        portfolio = self._portfolio_service.create_portfolio(owner_email, name)
        self._portfolio_service.deposit(portfolio.id, starting_balance, notes="paper trading starting balance")

        account_id = self._repository.save_account(
            PaperAccount(user_id=user_id, portfolio_id=portfolio.id, name=name, starting_balance=starting_balance)
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="ensure_account", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, user_id=user_id, account_id=account_id,
        )
        return self._repository.get_account(account_id)

    def sync_fill(self, account: PaperAccount, fill: Fill) -> Transaction:
        """Replays one paper `Fill` into the real Portfolio ledger as a
        genuine `buy`/`sell` transaction - cash/positions/P&L are never
        duplicated here, only reused from the existing, tested ledger."""
        notes = f"paper_trading order={fill.order_id} fill={fill.id}"
        if fill.side == OrderSide.BUY:
            return self._portfolio_service.buy(
                account.portfolio_id, fill.symbol, fill.quantity, fill.price, fee=fill.commission, tax=fill.tax,
                executed_at=fill.executed_at, notes=notes,
            )
        return self._portfolio_service.sell(
            account.portfolio_id, fill.symbol, fill.quantity, fill.price, fee=fill.commission, tax=fill.tax,
            executed_at=fill.executed_at, notes=notes,
        )

    def get_average_cost(self, account: PaperAccount, symbol: str) -> Optional[float]:
        """The real Portfolio ledger's average cost for `symbol` - `None`
        if the account holds no position in it (used by the scheduler to
        compute realized-gain tax on a closing SELL fill)."""
        position = self._portfolio_service.get_position(account.portfolio_id, symbol)
        return position.average_cost if position.quantity > 0 else None

    def sync_watchlist(self, account: PaperAccount, owner_email: str, symbol: str) -> None:
        """Automatically tracks every traded symbol in a dedicated
        "Paper Trading" watchlist for the account's owner."""
        if self._watchlist_service is None:
            return
        watchlist = self._get_or_create_paper_watchlist(owner_email)
        self._watchlist_service.add_symbol(watchlist.id, symbol)

    def sync_stop_take_profit_alert(self, account: PaperAccount, owner_email: str, order: Order) -> Optional[int]:
        """STOP/TAKE_PROFIT orders get a mirrored PRICE alert in the
        Watchlist & Alert Platform, so the user is notified through that
        existing channel too, independent of whether the scheduler in
        this package has executed the order yet."""
        if self._watchlist_repository is None or order.order_type not in (OrderType.STOP, OrderType.TAKE_PROFIT):
            return None

        triggers_above = (
            (order.order_type == OrderType.STOP and order.side == OrderSide.BUY)
            or (order.order_type == OrderType.TAKE_PROFIT and order.side == OrderSide.SELL)
        )
        alert_type = AlertType.PRICE_ABOVE if triggers_above else AlertType.PRICE_BELOW
        alert = Alert(
            owner=owner_email, symbol=order.symbol, category=AlertCategory.PRICE, alert_type=alert_type,
            parameters={"threshold": order.stop_price},
        )
        return self._watchlist_repository.save_alert(alert)

    def _get_or_create_paper_watchlist(self, owner_email: str):
        for watchlist in self._watchlist_service.list_watchlists(owner_email):
            if watchlist.name == _PAPER_WATCHLIST_NAME:
                return watchlist
        return self._watchlist_service.create_watchlist(owner_email, _PAPER_WATCHLIST_NAME)
