"""OptiTrade Watchlist & Alert Platform — exception types."""
from __future__ import annotations


class WatchlistError(Exception):
    """Base class for all Watchlist & Alert Platform errors."""


class WatchlistPersistenceError(WatchlistError):
    """Raised when a watchlist/alert record could not be read from or
    written to storage."""


class WatchlistNotFoundError(WatchlistError):
    """Raised when a requested watchlist_id does not exist."""


class WatchlistItemNotFoundError(WatchlistError):
    """Raised when a requested symbol does not exist in a watchlist."""


class AlertNotFoundError(WatchlistError):
    """Raised when a requested alert_id does not exist."""


class InvalidAlertError(WatchlistError):
    """Raised for a structurally invalid alert (wrong category/type
    combination, missing required parameters, ...)."""


class InsufficientAlertDataError(WatchlistError):
    """Raised when there isn't enough price/feature/news/portfolio data
    available to evaluate a given alert right now - never treated as a
    trigger, just skipped for this scan."""
