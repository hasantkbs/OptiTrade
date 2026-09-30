"""
OptiTrade ML Training Platform — feature extraction.

The ONLY module in this platform allowed to read raw feature values.
Auto-discovers every feature the Feature Store has for a symbol (via
`FeatureStoreService.list_feature_names`) rather than depending on a
hardcoded list, so a future engine's features are picked up
automatically the moment it starts writing them - no code change
needed here. Every value is resolved point-in-time
(`get_feature_as_of`), never "latest", so datasets built from this
extractor are never accidentally fed information from the future.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from ml_training.features import categories
from ml_training.models import FeatureVector

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """Reads point-in-time feature vectors from the Feature Store.
    Never computes a single feature value itself."""

    def __init__(self, feature_store: Optional[FeatureStoreService] = None) -> None:
        self.feature_store = feature_store or get_default_feature_store_service()

    def extract(
        self, symbol: str, as_of: Optional[datetime] = None, respect_ingestion_time: bool = False,
    ) -> FeatureVector:
        """`respect_ingestion_time=True` additionally excludes any
        feature record ingested after `as_of` - guards a historical
        `as_of` query against backfilled/reprocessed data (see
        `feature_store.offline_store.PostgresOfflineStore.get_as_of`'s
        docstring). Live inference (`as_of` defaults to "now") is
        unaffected either way; `ml_training.datasets.builder.
        DatasetBuilder` (training-dataset construction) opts in."""
        as_of = as_of or datetime.now(timezone.utc)
        feature_names = self.feature_store.list_feature_names(symbol)

        values = {}
        for name in feature_names:
            record = self.feature_store.get_feature_as_of(
                symbol, name, as_of, respect_ingestion_time=respect_ingestion_time
            )
            if record is not None:
                values[name] = record.value

        vector = FeatureVector(symbol=symbol, as_of=as_of, values=values, categories=categories.categorize(list(values.keys())))
        log_event(
            logger, component="ml_training", module="ml_training.features.extractor", operation="extract",
            status=STATUS_SUCCESS, symbol=symbol, feature_count=len(values),
        )
        return vector
