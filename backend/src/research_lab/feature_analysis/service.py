"""OptiTrade Research Lab — feature analysis service."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from research_lab.config import ResearchLabConfig
from research_lab.feature_analysis import correlation, drift, importance, stability
from research_lab.feature_analysis.repository import FeatureAnalysisRepository
from research_lab.models import (
    FeatureCorrelationRecord,
    FeatureDriftRecord,
    FeatureImportanceRecord,
    FeatureStabilityRecord,
)

logger = logging.getLogger(__name__)


class FeatureAnalysisService:
    """Dependency-injectable facade tying feature importance/
    correlation/stability/drift together. Reads historical features
    exclusively through the Feature Store - never a second data path."""

    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        repository: Optional[FeatureAnalysisRepository] = None,
        config: Optional[ResearchLabConfig] = None,
    ) -> None:
        self.feature_store = feature_store or get_default_feature_store_service()
        self.repository = repository or FeatureAnalysisRepository()
        self.config = config or ResearchLabConfig.from_env()

    def record_importance(
        self, symbol: str, engine_name: str, feature_importance: Dict[str, float],
    ) -> List[FeatureImportanceRecord]:
        records = importance.to_records(symbol, engine_name, feature_importance)
        for record in records:
            self.repository.save_importance(record)
        log_event(
            logger, component="research_lab", module="research_lab.feature_analysis.service",
            operation="record_importance", status=STATUS_SUCCESS, symbol=symbol,
            engine_name=engine_name, feature_count=len(records),
        )
        return records

    def get_importance_history(
        self, symbol: str, engine_name: str, feature_name: str, limit: int = 50,
    ) -> List[FeatureImportanceRecord]:
        return self.repository.get_importance_history(symbol, engine_name, feature_name, limit)

    def analyze_correlation(
        self, symbol: str, feature_a: str, feature_b: str, start: datetime, end: datetime,
    ) -> Optional[FeatureCorrelationRecord]:
        record = correlation.compute_correlation(self.feature_store, symbol, feature_a, feature_b, start, end)
        if record is not None:
            self.repository.save_correlation(record)
        return record

    def analyze_stability(
        self, symbol: str, feature_name: str, start: datetime, end: datetime,
    ) -> Optional[FeatureStabilityRecord]:
        record = stability.compute_stability(self.feature_store, symbol, feature_name, start, end)
        if record is not None:
            self.repository.save_stability(record)
        return record

    def analyze_drift(
        self, symbol: str, feature_name: str,
        baseline_start: datetime, baseline_end: datetime, recent_start: datetime, recent_end: datetime,
    ) -> Optional[FeatureDriftRecord]:
        record = drift.compute_drift(
            self.feature_store, symbol, feature_name,
            baseline_start, baseline_end, recent_start, recent_end, self.config,
        )
        if record is not None:
            self.repository.save_drift(record)
        return record
