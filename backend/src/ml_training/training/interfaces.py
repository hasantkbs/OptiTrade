"""
OptiTrade ML Training Platform — trainer interface.

Every algorithm (LightGBM, XGBoost, CatBoost, Random Forest) satisfies
this exact `Protocol`, so `optimization/`, `evaluation/`, `calibration/`,
`importance/`, and `registry/` never need to know which concrete
algorithm they're working with.
"""
from __future__ import annotations

from typing import Dict, Optional, Protocol, runtime_checkable

import numpy as np

from ml_training.models import ModelAlgorithm, TaskType


@runtime_checkable
class ModelTrainerProtocol(Protocol):
    algorithm: ModelAlgorithm
    task_type: TaskType

    def fit(
        self, X_train: np.ndarray, y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
    ) -> None: ...

    def predict(self, X: np.ndarray) -> np.ndarray: ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...

    def feature_importance(self) -> Dict[str, float]: ...

    def save(self, path: str) -> None: ...

    def load(self, path: str) -> None: ...
