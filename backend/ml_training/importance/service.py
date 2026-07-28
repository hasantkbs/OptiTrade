"""
OptiTrade ML Training Platform — feature importance service.

Computes SHAP and permutation importance, then stores the result in
BOTH places the architecture already has for exactly this purpose:

  - The Feature Store (`FeatureStoreService.write_feature`), so
    importance is queryable/historical the same way every other
    feature is.
  - Research Lab's feature analysis
    (`research_lab.feature_analysis.service.FeatureAnalysisService.
    record_importance`, reused directly rather than re-implemented -
    it already has exactly this "symbol + engine_name + feature
    importance dict" shape).
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from core.structured_logging import STATUS_SUCCESS, log_event
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from ml_training.config import MLTrainingConfig
from ml_training.importance import permutation_analyzer, shap_analyzer
from ml_training.models import FeatureImportanceEntry, ImportanceMethod
from ml_training.training.base import BaseTrainer
from research_lab.feature_analysis.service import FeatureAnalysisService

logger = logging.getLogger(__name__)


class FeatureImportanceService:
    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        feature_analysis_service: Optional[FeatureAnalysisService] = None,
        config: Optional[MLTrainingConfig] = None,
    ) -> None:
        self.config = config or MLTrainingConfig.from_env()
        self.feature_store = feature_store or FeatureStoreService()
        self.feature_analysis_service = feature_analysis_service or FeatureAnalysisService(
            feature_store=self.feature_store,
        )

    def compute_and_persist_shap(
        self, model_id: str, trainer: BaseTrainer, X_background: np.ndarray,
    ) -> List[FeatureImportanceEntry]:
        importance_dict = shap_analyzer.compute_shap_importance(trainer._model, X_background, trainer.feature_names)
        return self._persist(model_id, importance_dict, ImportanceMethod.SHAP)

    def compute_and_persist_permutation(
        self, model_id: str, trainer: BaseTrainer, X: np.ndarray, y: np.ndarray,
    ) -> List[FeatureImportanceEntry]:
        importance_dict = permutation_analyzer.compute_permutation_importance(
            trainer, X, y, random_state=self.config.random_state,
        )
        return self._persist(model_id, importance_dict, ImportanceMethod.PERMUTATION)

    def _persist(self, model_id: str, importance_dict: dict, method: ImportanceMethod) -> List[FeatureImportanceEntry]:
        self.feature_analysis_service.record_importance(
            symbol=model_id, engine_name=f"MLModel:{method.value}", feature_importance=importance_dict,
        )

        entries: List[FeatureImportanceEntry] = []
        for feature_name, importance in importance_dict.items():
            self.feature_store.write_feature(
                FeatureValue(symbol=model_id, feature_name=f"{method.value}_importance:{feature_name}", value=importance)
            )
            entries.append(
                FeatureImportanceEntry(model_id=model_id, feature_name=feature_name, importance=importance, method=method)
            )

        log_event(
            logger, component="ml_training", module="ml_training.importance.service", operation="persist",
            status=STATUS_SUCCESS, model_id=model_id, method=method.value, feature_count=len(entries),
        )
        return entries
