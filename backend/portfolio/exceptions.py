"""OptiTrade Portfolio Intelligence Platform — exception types."""
from __future__ import annotations


class PortfolioError(Exception):
    """Base class for all Portfolio Intelligence Platform errors."""


class PortfolioPersistenceError(PortfolioError):
    """Raised when a portfolio record could not be read from or written
    to storage."""


class PortfolioNotFoundError(PortfolioError):
    """Raised when a requested portfolio_id does not exist."""


class InsufficientCashError(PortfolioError):
    """Raised when a BUY/WITHDRAWAL transaction would drive a
    portfolio's cash balance negative."""


class InsufficientPositionError(PortfolioError):
    """Raised when a SELL transaction would drive a position's quantity
    negative."""


class InvalidTransactionError(PortfolioError):
    """Raised for a structurally invalid transaction (e.g. a BUY/SELL
    with no symbol, a non-positive quantity/price)."""


class InsufficientPriceDataError(PortfolioError):
    """Raised when there isn't enough historical price data to compute
    a requested risk/optimization/scenario result."""
