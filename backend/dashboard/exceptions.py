"""OptiTrade Analytics & Dashboard Platform — exception types."""
from __future__ import annotations


class DashboardError(Exception):
    """Base class for all Analytics & Dashboard Platform errors."""


class DashboardPersistenceError(DashboardError):
    """Raised when a record could not be read from storage."""


class InvalidReportRequestError(DashboardError):
    pass
