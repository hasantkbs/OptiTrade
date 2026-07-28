"""
OptiTrade ML Training Platform — shared trainer base.

Every concrete algorithm trainer only needs to implement `fit()` (each
library's constructor/eval_set API differs enough that a fully-generic
`fit()` isn't worth the abstraction) - `predict`, `predict_proba`,
`feature_importance`, `save`, and `load` are identical across all four
algorithms because LightGBM/XGBoost/CatBoost all expose scikit-learn-
compatible estimator classes (`LGBMClassifier`/`XGBClassifier`/
`CatBoostClassifier`, ...) with the exact same `.predict()`/
`.predict_proba()`/`.feature_importances_` surface scikit-learn's own
`RandomForestClassifier` already has - deliberately used here instead
of each library's native Booster API specifically so this one base
class can serve all four uniformly.

Persistence reuses `joblib` - the same library `core/ml_predictor.py`'s
existing `models/xgb_signal_model.joblib` was already saved with.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import joblib
import numpy as np

from core.structured_logging import STATUS_SUCCESS, log_event
from ml_training.config import MLTrainingConfig
from ml_training.exceptions import ModelNotFittedError
from ml_training.models import ModelAlgorithm, TaskType

logger = logging.getLogger(__name__)


class BaseTrainer:
    """Not directly instantiated - subclasses set `algorithm` and
    implement `fit()`."""

    algorithm: ModelAlgorithm

    def __init__(
        self,
        task_type: TaskType,
        feature_names: List[str],
        hyperparameters: Optional[Dict] = None,
        config: Optional[MLTrainingConfig] = None,
    ) -> None:
        self.task_type = task_type
        self.feature_names = list(feature_names)
        self.hyperparameters = dict(hyperparameters or {})
        self.config = config or MLTrainingConfig()
        self._model = None

    @property
    def is_fitted(self) -> bool:
        return self._model is not None

    def fit(
        self, X_train: np.ndarray, y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
    ) -> None:
        raise NotImplementedError

    def predict(self, X: np.ndarray) -> np.ndarray:
        self._require_fitted()
        return np.asarray(self._model.predict(X))

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        self._require_fitted()
        if self.task_type != TaskType.CLASSIFICATION:
            raise ValueError(
                f"{self.algorithm.value}: predict_proba is only defined for classification "
                f"tasks - this trainer's task_type is {self.task_type.value}"
            )
        return np.asarray(self._model.predict_proba(X))

    def feature_importance(self) -> Dict[str, float]:
        self._require_fitted()
        raw = np.asarray(self._model.feature_importances_, dtype=float)
        total = float(raw.sum())
        normalized = raw / total if total > 0 else raw
        return dict(zip(self.feature_names, (float(v) for v in normalized)))

    def save(self, path: str) -> None:
        self._require_fitted()
        joblib.dump(
            {
                "algorithm": self.algorithm.value, "model": self._model,
                "feature_names": self.feature_names, "task_type": self.task_type.value,
                "hyperparameters": self.hyperparameters,
            },
            path,
        )
        log_event(
            logger, component="ml_training", module="ml_training.training.base", operation="save",
            status=STATUS_SUCCESS, algorithm=self.algorithm.value, path=path,
        )

    def load(self, path: str) -> None:
        payload = joblib.load(path)
        self._model = payload["model"]
        self.feature_names = payload["feature_names"]
        self.task_type = TaskType(payload["task_type"])
        self.hyperparameters = payload["hyperparameters"]
        log_event(
            logger, component="ml_training", module="ml_training.training.base", operation="load",
            status=STATUS_SUCCESS, algorithm=self.algorithm.value, path=path,
        )

    def _require_fitted(self) -> None:
        if not self.is_fitted:
            raise ModelNotFittedError(f"{self.algorithm.value} trainer has not been fit yet")
