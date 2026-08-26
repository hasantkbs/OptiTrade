"""
OptiTrade Feature Store — structural interfaces (Protocols).

Mirrors the pattern established in `core/interfaces.py` (Sprint 1): each
`Protocol` names only the methods the service layer actually calls, so
future engines (Decision Engine, Technical Engine, Fundamental Engine,
News Engine, ...) can be typed and tested against these instead of the
concrete Redis/PostgreSQL-backed implementations.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Protocol, runtime_checkable

from feature_store.models import FeatureRecord, FeatureValue, ValidationResult


@runtime_checkable
class OnlineFeatureStoreProtocol(Protocol):
    """Contract for the low-latency 'latest value only' cache (Redis-backed).

    Implementations must never raise for their own backend-connectivity
    failures — `get_latest` degrades to `None` (treated as a cache miss)
    and `set_latest` degrades to a no-op; only `ping()` reports failure,
    via its boolean return value. This is a cache, not a source of truth.
    """

    def get_latest(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]: ...

    def set_latest(self, record: FeatureRecord) -> None: ...

    def ping(self) -> bool: ...


@runtime_checkable
class OfflineFeatureStoreProtocol(Protocol):
    """Contract for the durable, versioned, point-in-time-queryable store (PostgreSQL-backed)."""

    def insert(self, record: FeatureRecord) -> None: ...

    def get_latest(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]: ...

    def get_as_of(
        self, symbol: str, feature_name: str, as_of: datetime, respect_ingestion_time: bool = False,
    ) -> Optional[FeatureRecord]: ...

    def get_history(
        self, symbol: str, feature_name: str, start: datetime, end: datetime
    ) -> List[FeatureRecord]: ...

    def list_feature_names(self, symbol: str) -> List[str]: ...

    def ping(self) -> bool: ...


@runtime_checkable
class FeatureValidatorProtocol(Protocol):
    """Contract for pre-write feature validation."""

    def validate(self, feature: FeatureValue) -> ValidationResult: ...
