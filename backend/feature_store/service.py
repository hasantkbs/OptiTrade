"""
OptiTrade Feature Store — service facade.

The single public entry point every future engine (Decision Engine,
Technical Engine, Fundamental Engine, News Engine, ...) depends on — they
should type against `feature_store.interfaces` / call
`FeatureStoreService`, never construct `RedisOnlineStore`/
`PostgresOfflineStore` directly.

Write path: validate -> offline store (source of truth, append-only) ->
online store (best-effort cache refresh; a cache-side failure is logged
but never fails the write, since the offline store already has the
durable record).

Read path ("latest"): online store first (fast path); on a cache miss,
fall back to the offline store and repopulate the online store
(read-through).

Read path ("as of"): offline store only, always — the online store never
holds historical data.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.exceptions import FeatureValidationError
from feature_store.interfaces import (
    FeatureValidatorProtocol,
    OfflineFeatureStoreProtocol,
    OnlineFeatureStoreProtocol,
)
from feature_store.models import FeatureRecord, FeatureValue
from feature_store.offline_store import PostgresOfflineStore
from feature_store.online_store import RedisOnlineStore
from feature_store.validation import FeatureValidator

logger = logging.getLogger(__name__)


class FeatureStoreService:
    """Dependency-injectable facade over the online/offline feature stores
    and the validator. Every constructor parameter is optional and falls
    back to the real, config-driven implementation — matching the
    dependency-injection pattern established for
    `core.hybrid_engine.HybridTradingEngine` in Sprint 1."""

    def __init__(
        self,
        online_store: Optional[OnlineFeatureStoreProtocol] = None,
        offline_store: Optional[OfflineFeatureStoreProtocol] = None,
        validator: Optional[FeatureValidatorProtocol] = None,
    ) -> None:
        self.online_store: OnlineFeatureStoreProtocol = online_store or RedisOnlineStore()
        self.offline_store: OfflineFeatureStoreProtocol = offline_store or PostgresOfflineStore()
        self.validator: FeatureValidatorProtocol = validator or FeatureValidator()

    def write_feature(self, feature: FeatureValue) -> FeatureRecord:
        """Validates, then durably persists, a single feature value."""
        result = self.validator.validate(feature)
        if not result.is_valid:
            raise FeatureValidationError(feature.symbol, feature.feature_name, result.errors)

        record = FeatureRecord(
            **feature.model_dump(),
            ingestion_timestamp=datetime.now(timezone.utc),
        )
        self.offline_store.insert(record)

        try:
            self.online_store.set_latest(record)
        except Exception as exc:
            log_event(
                logger,
                component="feature_store",
                module="feature_store.service",
                operation="cache_refresh",
                status=STATUS_ERROR,
                symbol=record.symbol,
                feature_name=record.feature_name,
                error_type=type(exc).__name__,
                level=logging.WARNING,
            )
        return record

    def write_features(
        self,
        symbol: str,
        values: Dict[str, float],
        version: str = "v1",
        event_timestamp: Optional[datetime] = None,
    ) -> List[FeatureRecord]:
        """Convenience batch write for multiple named features on one symbol,
        all sharing the same event_timestamp."""
        timestamp = event_timestamp or datetime.now(timezone.utc)
        return [
            self.write_feature(
                FeatureValue(
                    symbol=symbol, feature_name=name, value=value,
                    version=version, event_timestamp=timestamp,
                )
            )
            for name, value in values.items()
        ]

    def get_latest_feature(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]:
        """Read-through: online store first, offline store on a miss
        (repopulating the online store from the result)."""
        cached = self.online_store.get_latest(symbol, feature_name)
        if cached is not None:
            return cached

        record = self.offline_store.get_latest(symbol, feature_name)
        if record is not None:
            try:
                self.online_store.set_latest(record)
            except Exception as exc:
                log_event(
                    logger,
                    component="feature_store",
                    module="feature_store.service",
                    operation="cache_refresh",
                    status=STATUS_ERROR,
                    symbol=symbol,
                    feature_name=feature_name,
                    error_type=type(exc).__name__,
                    level=logging.WARNING,
                )
        return record

    def get_latest_features(self, symbol: str, feature_names: List[str]) -> Dict[str, float]:
        """Batch convenience wrapper — omits any feature_name with no
        recorded value rather than raising."""
        result: Dict[str, float] = {}
        for name in feature_names:
            record = self.get_latest_feature(symbol, name)
            if record is not None:
                result[name] = record.value
        return result

    def get_feature_as_of(
        self, symbol: str, feature_name: str, as_of: datetime
    ) -> Optional[FeatureRecord]:
        """Point-in-time lookup — always goes to the offline store, never
        the online cache, since the cache only ever holds the latest value."""
        return self.offline_store.get_as_of(symbol, feature_name, as_of)

    def health_check(self) -> Dict[str, Any]:
        """Connectivity monitoring hook for both backing stores. Not wired
        into any HTTP endpoint yet — a future API-integration step can
        expose this (e.g. as `/feature-store/health`)."""
        try:
            online_ok = self.online_store.ping()
        except Exception:
            online_ok = False
        try:
            offline_ok = self.offline_store.ping()
        except Exception:
            offline_ok = False

        status = STATUS_SUCCESS if (online_ok and offline_ok) else STATUS_ERROR
        log_event(
            logger,
            component="feature_store",
            module="feature_store.service",
            operation="health_check",
            status=status,
            online_store_available=online_ok,
            offline_store_available=offline_ok,
        )
        return {"online_store_available": online_ok, "offline_store_available": offline_ok}
