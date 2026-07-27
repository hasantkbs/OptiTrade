"""
OptiTrade Decision Engine — accuracy-weight lookup.

Per-engine accuracy weights come from the Feature Store: each engine's
historical accuracy is stored there as a feature keyed by
(entity=engine_name, feature_name=<accuracy_feature_name>). If no
historical value has ever been written for an engine, its weight
defaults to `DecisionEngineConfig.default_accuracy_weight` (1.0) — new or
never-scored engines are neither penalized nor favored until real
accuracy history exists (populated by a later Continuous Learning step,
out of scope here).
"""
from __future__ import annotations

import logging

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.config import DecisionEngineConfig
from feature_store.interfaces import OfflineFeatureStoreProtocol, OnlineFeatureStoreProtocol
from feature_store.service import FeatureStoreService

logger = logging.getLogger(__name__)


class AccuracyWeightProvider:
    """Looks up each voting engine's current accuracy weight via the
    Feature Store, falling back to a configured default."""

    def __init__(
        self,
        feature_store: FeatureStoreService,
        config: DecisionEngineConfig,
    ) -> None:
        self._feature_store = feature_store
        self._config = config

    def get_weight(self, engine_name: str) -> float:
        record = self._feature_store.get_latest_feature(
            engine_name, self._config.accuracy_feature_name
        )
        weight = record.value if record is not None else self._config.default_accuracy_weight
        log_event(
            logger,
            component="decision_engine",
            module="decision_engine.weighting",
            operation="get_weight",
            status=STATUS_SUCCESS,
            engine_name=engine_name,
            weight=weight,
            used_default=record is None,
        )
        return weight
