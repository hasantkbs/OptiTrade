"""OptiTrade ML Training Platform — LightGBM trainer."""
from __future__ import annotations

from typing import Optional

import lightgbm as lgb
import numpy as np

from ml_training.models import ModelAlgorithm, TaskType
from ml_training.training.base import BaseTrainer


class LightGBMTrainer(BaseTrainer):
    algorithm = ModelAlgorithm.LIGHTGBM

    def fit(
        self, X_train: np.ndarray, y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
    ) -> None:
        params = {"random_state": self.config.random_state, "verbose": -1, **self.hyperparameters}
        self._model = (
            lgb.LGBMClassifier(**params) if self.task_type == TaskType.CLASSIFICATION
            else lgb.LGBMRegressor(**params)
        )

        y_train_encoded = self._encode_y(y_train, fit_encoder=True)
        fit_kwargs = {}
        if X_val is not None and y_val is not None:
            fit_kwargs["eval_X"] = X_val
            fit_kwargs["eval_y"] = self._encode_y(y_val, fit_encoder=False)
            fit_kwargs["callbacks"] = [lgb.early_stopping(self.config.early_stopping_rounds, verbose=False)]

        self._model.fit(X_train, y_train_encoded, **fit_kwargs)
