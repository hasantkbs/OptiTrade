"""OptiTrade Paper Trading & Trade Journal Platform — exception types."""
from __future__ import annotations


class PaperTradingError(Exception):
    """Base class for all Paper Trading Platform errors."""


class PaperTradingPersistenceError(PaperTradingError):
    """Raised when a record could not be read from or written to storage."""


class ValidationFailedError(PaperTradingError):
    pass


class AccountNotFoundError(PaperTradingError):
    pass


class OrderNotFoundError(PaperTradingError):
    pass


class InvalidOrderError(PaperTradingError):
    """Raised for structurally invalid order parameters (bad price/
    quantity combination for the given order type)."""


class OrderNotOpenError(PaperTradingError):
    """Raised when cancelling/modifying an order that is already
    filled, cancelled, rejected, or expired."""


class InsufficientPaperCashError(PaperTradingError):
    pass


class InsufficientPaperPositionError(PaperTradingError):
    pass


class MarketClosedError(PaperTradingError):
    """Raised when a market order is placed outside the traded symbol's
    validated trading hours."""


class JournalEntryNotFoundError(PaperTradingError):
    pass
