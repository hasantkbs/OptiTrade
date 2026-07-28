"""
OptiTrade Portfolio Intelligence Platform — Portfolio Service
(requirement 1).

Every mutation is an appended `Transaction` - cash balance, positions,
and realized P&L are always *replayed* from the full transaction
history (weighted-average-cost accounting), never stored as a second,
independently-mutable copy. This is the ledger-accounting equivalent of
`research_lab.datasets`/`ml_training.datasets`'s "definition only,
never a data copy" philosophy: the transaction log is the single source
of truth.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from portfolio.config import PortfolioConfig
from portfolio.exceptions import (
    InsufficientCashError,
    InsufficientPositionError,
    InvalidTransactionError,
    PortfolioNotFoundError,
)
from portfolio.models import Portfolio, PortfolioSnapshot, Position, Transaction, TransactionType
from portfolio.prices import PriceService
from portfolio.repository import PortfolioRepository

logger = logging.getLogger(__name__)

_TRADE_TYPES = {TransactionType.BUY, TransactionType.SELL}


class _PositionState:
    __slots__ = ("quantity", "average_cost", "realized_pnl")

    def __init__(self) -> None:
        self.quantity = 0.0
        self.average_cost = 0.0
        self.realized_pnl = 0.0


def _replay_cash(transactions: List[Transaction]) -> float:
    cash = 0.0
    for txn in transactions:
        if txn.transaction_type == TransactionType.DEPOSIT:
            cash += txn.amount
        elif txn.transaction_type == TransactionType.WITHDRAWAL:
            cash -= txn.amount
        elif txn.transaction_type == TransactionType.BUY:
            cash -= txn.amount + txn.fee + txn.tax
        elif txn.transaction_type == TransactionType.SELL:
            cash += txn.amount - txn.fee - txn.tax
        elif txn.transaction_type == TransactionType.DIVIDEND:
            cash += txn.amount - txn.fee - txn.tax
        elif txn.transaction_type == TransactionType.FEE:
            cash -= txn.amount
        elif txn.transaction_type == TransactionType.TAX:
            cash -= txn.amount
    return cash


def _replay_positions(transactions: List[Transaction]) -> Dict[str, _PositionState]:
    states: Dict[str, _PositionState] = {}
    for txn in transactions:
        if txn.symbol is None or txn.transaction_type not in _TRADE_TYPES:
            continue
        state = states.setdefault(txn.symbol, _PositionState())
        if txn.transaction_type == TransactionType.BUY:
            new_quantity = state.quantity + txn.quantity
            cost_basis = state.average_cost * state.quantity + txn.price * txn.quantity + txn.fee + txn.tax
            state.average_cost = (cost_basis / new_quantity) if new_quantity > 0 else 0.0
            state.quantity = new_quantity
        else:  # SELL
            state.realized_pnl += (txn.price - state.average_cost) * txn.quantity - txn.fee - txn.tax
            state.quantity -= txn.quantity
            if state.quantity <= 0.0:
                state.quantity = 0.0
                state.average_cost = 0.0
    return states


class PortfolioService:
    def __init__(
        self,
        repository: Optional[PortfolioRepository] = None,
        price_service: Optional[PriceService] = None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        self.repository = repository or PortfolioRepository()
        self.price_service = price_service or PriceService(config=self.config)

    # ── Portfolios ───────────────────────────────────────────────────────

    def create_portfolio(self, owner: str, name: str, base_currency: Optional[str] = None) -> Portfolio:
        portfolio = Portfolio(owner=owner, name=name, base_currency=base_currency or self.config.default_base_currency)
        portfolio.id = self.repository.save_portfolio(portfolio)
        log_event(
            logger, component="portfolio", module="portfolio.service", operation="create_portfolio",
            status=STATUS_SUCCESS, portfolio_id=portfolio.id, owner=owner,
        )
        return portfolio

    def get_portfolio(self, portfolio_id: int) -> Portfolio:
        portfolio = self.repository.get_portfolio(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(f"no portfolio with id {portfolio_id!r}")
        return portfolio

    def list_portfolios(self, owner: str) -> List[Portfolio]:
        return self.repository.list_portfolios(owner)

    # ── Cash transactions ────────────────────────────────────────────────

    def deposit(self, portfolio_id: int, amount: float, currency: Optional[str] = None,
                executed_at: Optional[datetime] = None, notes: str = "") -> Transaction:
        portfolio = self.get_portfolio(portfolio_id)
        return self._record(
            portfolio_id, TransactionType.DEPOSIT, amount=amount,
            currency=currency or portfolio.base_currency, executed_at=executed_at, notes=notes,
        )

    def withdraw(self, portfolio_id: int, amount: float, currency: Optional[str] = None,
                 executed_at: Optional[datetime] = None, notes: str = "") -> Transaction:
        portfolio = self.get_portfolio(portfolio_id)
        cash = self.get_cash_balance(portfolio_id)
        if amount > cash:
            raise InsufficientCashError(
                f"portfolio {portfolio_id}: cannot withdraw {amount} - only {cash} cash available"
            )
        return self._record(
            portfolio_id, TransactionType.WITHDRAWAL, amount=amount,
            currency=currency or portfolio.base_currency, executed_at=executed_at, notes=notes,
        )

    # ── Trades ───────────────────────────────────────────────────────────

    def buy(self, portfolio_id: int, symbol: str, quantity: float, price: float, fee: float = 0.0,
            tax: float = 0.0, currency: Optional[str] = None, executed_at: Optional[datetime] = None,
            notes: str = "") -> Transaction:
        if quantity <= 0 or price <= 0:
            raise InvalidTransactionError("a BUY requires a positive quantity and price")
        portfolio = self.get_portfolio(portfolio_id)
        total_cost = quantity * price + fee + tax
        cash = self.get_cash_balance(portfolio_id)
        if total_cost > cash:
            raise InsufficientCashError(
                f"portfolio {portfolio_id}: cannot buy {quantity} {symbol} at {price} - "
                f"total cost {total_cost} exceeds available cash {cash}"
            )
        return self._record(
            portfolio_id, TransactionType.BUY, symbol=symbol, quantity=quantity, price=price,
            amount=quantity * price, fee=fee, tax=tax, currency=currency or portfolio.base_currency,
            executed_at=executed_at, notes=notes,
        )

    def sell(self, portfolio_id: int, symbol: str, quantity: float, price: float, fee: float = 0.0,
             tax: float = 0.0, currency: Optional[str] = None, executed_at: Optional[datetime] = None,
             notes: str = "") -> Transaction:
        if quantity <= 0 or price <= 0:
            raise InvalidTransactionError("a SELL requires a positive quantity and price")
        portfolio = self.get_portfolio(portfolio_id)
        position = self.get_position(portfolio_id, symbol)
        if quantity > position.quantity:
            raise InsufficientPositionError(
                f"portfolio {portfolio_id}: cannot sell {quantity} {symbol} - only {position.quantity} held"
            )
        return self._record(
            portfolio_id, TransactionType.SELL, symbol=symbol, quantity=quantity, price=price,
            amount=quantity * price, fee=fee, tax=tax, currency=currency or portfolio.base_currency,
            executed_at=executed_at, notes=notes,
        )

    # ── Dividends / fees / taxes ─────────────────────────────────────────

    def record_dividend(self, portfolio_id: int, symbol: str, amount: float, tax: float = 0.0,
                        currency: Optional[str] = None, executed_at: Optional[datetime] = None,
                        notes: str = "") -> Transaction:
        portfolio = self.get_portfolio(portfolio_id)
        return self._record(
            portfolio_id, TransactionType.DIVIDEND, symbol=symbol, amount=amount, tax=tax,
            currency=currency or portfolio.base_currency, executed_at=executed_at, notes=notes,
        )

    def record_fee(self, portfolio_id: int, amount: float, symbol: Optional[str] = None,
                   currency: Optional[str] = None, executed_at: Optional[datetime] = None,
                   notes: str = "") -> Transaction:
        portfolio = self.get_portfolio(portfolio_id)
        return self._record(
            portfolio_id, TransactionType.FEE, symbol=symbol, amount=amount,
            currency=currency or portfolio.base_currency, executed_at=executed_at, notes=notes,
        )

    def record_tax(self, portfolio_id: int, amount: float, symbol: Optional[str] = None,
                   currency: Optional[str] = None, executed_at: Optional[datetime] = None,
                   notes: str = "") -> Transaction:
        portfolio = self.get_portfolio(portfolio_id)
        return self._record(
            portfolio_id, TransactionType.TAX, symbol=symbol, amount=amount,
            currency=currency or portfolio.base_currency, executed_at=executed_at, notes=notes,
        )

    def list_transactions(self, portfolio_id: int, symbol: Optional[str] = None) -> List[Transaction]:
        self.get_portfolio(portfolio_id)
        return self.repository.list_transactions(portfolio_id, symbol)

    # ── Positions / cash / P&L (replayed, never stored directly) ────────

    def get_cash_balance(self, portfolio_id: int) -> float:
        self.get_portfolio(portfolio_id)
        return _replay_cash(self.repository.list_transactions(portfolio_id))

    def get_positions(self, portfolio_id: int) -> List[Position]:
        """Only currently-open (quantity > 0) positions - a fully
        closed position's realized P&L still counts toward
        `get_realized_pnl`, it just isn't listed as a holding anymore."""
        self.get_portfolio(portfolio_id)
        states = _replay_positions(self.repository.list_transactions(portfolio_id))
        return [
            Position(portfolio_id=portfolio_id, symbol=symbol, quantity=state.quantity,
                      average_cost=state.average_cost, realized_pnl=state.realized_pnl)
            for symbol, state in states.items() if state.quantity > 0.0
        ]

    def get_position(self, portfolio_id: int, symbol: str) -> Position:
        symbol = symbol.upper()
        states = _replay_positions(self.repository.list_transactions(portfolio_id, symbol=symbol))
        state = states.get(symbol)
        if state is None:
            return Position(portfolio_id=portfolio_id, symbol=symbol, quantity=0.0, average_cost=0.0, realized_pnl=0.0)
        return Position(
            portfolio_id=portfolio_id, symbol=symbol, quantity=state.quantity,
            average_cost=state.average_cost, realized_pnl=state.realized_pnl,
        )

    def get_realized_pnl(self, portfolio_id: int) -> float:
        """Sums realized P&L across every symbol ever traded, including
        positions since fully closed - unlike `get_positions`, this is
        never filtered to currently-open holdings."""
        self.get_portfolio(portfolio_id)
        states = _replay_positions(self.repository.list_transactions(portfolio_id))
        return sum(state.realized_pnl for state in states.values())

    def get_unrealized_pnl(self, portfolio_id: int) -> float:
        positions = self.get_positions(portfolio_id)
        total = 0.0
        for position in positions:
            current_price = self.price_service.get_current_price(position.symbol)
            total += (current_price - position.average_cost) * position.quantity
        return total

    def get_total_value(self, portfolio_id: int) -> float:
        positions = self.get_positions(portfolio_id)
        positions_value = sum(
            position.quantity * self.price_service.get_current_price(position.symbol) for position in positions
        )
        return self.get_cash_balance(portfolio_id) + positions_value

    # ── History (requirement 1's "portfolio history") ───────────────────

    def take_snapshot(self, portfolio_id: int) -> PortfolioSnapshot:
        self.get_portfolio(portfolio_id)
        positions = self.get_positions(portfolio_id)
        cash_balance = self.get_cash_balance(portfolio_id)
        positions_value = 0.0
        unrealized_pnl = 0.0
        for position in positions:
            current_price = self.price_service.get_current_price(position.symbol)
            positions_value += position.quantity * current_price
            unrealized_pnl += (current_price - position.average_cost) * position.quantity

        snapshot = PortfolioSnapshot(
            portfolio_id=portfolio_id, as_of=datetime.now(timezone.utc), cash_balance=cash_balance,
            positions_value=positions_value, total_value=cash_balance + positions_value,
            unrealized_pnl=unrealized_pnl, realized_pnl=self.get_realized_pnl(portfolio_id),
        )
        snapshot.id = self.repository.save_snapshot(snapshot)
        log_event(
            logger, component="portfolio", module="portfolio.service", operation="take_snapshot",
            status=STATUS_SUCCESS, portfolio_id=portfolio_id, total_value=snapshot.total_value,
        )
        return snapshot

    def get_history(self, portfolio_id: int, limit: int = 100) -> List[PortfolioSnapshot]:
        self.get_portfolio(portfolio_id)
        return self.repository.list_snapshots(portfolio_id, limit)

    # ── Internals ────────────────────────────────────────────────────────

    def _record(
        self, portfolio_id: int, transaction_type: TransactionType, amount: float, symbol: Optional[str] = None,
        quantity: Optional[float] = None, price: Optional[float] = None, fee: float = 0.0, tax: float = 0.0,
        currency: str = "USD", executed_at: Optional[datetime] = None, notes: str = "",
    ) -> Transaction:
        transaction = Transaction(
            portfolio_id=portfolio_id, transaction_type=transaction_type, symbol=symbol, quantity=quantity,
            price=price, amount=amount, fee=fee, tax=tax, currency=currency,
            executed_at=executed_at or datetime.now(timezone.utc), notes=notes,
        )
        transaction.id = self.repository.save_transaction(transaction)
        log_event(
            logger, component="portfolio", module="portfolio.service", operation="record_transaction",
            status=STATUS_SUCCESS, portfolio_id=portfolio_id, transaction_type=transaction_type.value,
            transaction_id=transaction.id, symbol=symbol,
        )
        return transaction
