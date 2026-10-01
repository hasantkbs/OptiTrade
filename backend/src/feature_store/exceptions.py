"""OptiTrade Feature Store — exception types."""
from __future__ import annotations

from typing import List


class FeatureStoreError(Exception):
    """Base class for all feature store errors."""


class FeatureValidationError(FeatureStoreError):
    """Raised when a feature value fails validation before being written."""

    def __init__(self, symbol: str, feature_name: str, errors: List[str]) -> None:
        self.symbol = symbol
        self.feature_name = feature_name
        self.errors = errors
        super().__init__(
            f"Invalid feature {feature_name!r} for {symbol!r}: {'; '.join(errors)}"
        )


class FeatureNotFoundError(FeatureStoreError):
    """Raised when a requested feature has no recorded value."""

    def __init__(self, symbol: str, feature_name: str) -> None:
        self.symbol = symbol
        self.feature_name = feature_name
        super().__init__(f"No value found for feature {feature_name!r} on {symbol!r}")
