"""
OptiTrade ML Training Platform — Random Forest trainer.

Random forests are not boosted/iterative, so there is no early-
stopping concept here - `X_val`/`y_val`, if given, are simply unused
(accepted only to satisfy `ModelTrainerProtocol`'s uniform signature).
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from ml_training.models import ModelAlgorithm, TaskType
from ml_training.training.base import BaseTrainer


class RandomForestTrainer(BaseTrainer):
    algorithm = ModelAlgorithm.RANDOM_FOREST

    def fit(
        self, X_train: np.ndarray, y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
    ) -> None:
        params = {"random_state": self.config.random_state, **self.hyperparameters}
        self._model = (
            RandomForestClassifier(**params) if self.task_type == TaskType.CLASSIFICATION
            else RandomForestRegressor(**params)
        )
        y_train_encoded = self._encode_y(y_train, fit_encoder=True)
        self._model.fit(X_train, y_train_encoded)
