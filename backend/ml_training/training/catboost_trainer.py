"""OptiTrade ML Training Platform — CatBoost trainer."""
from __future__ import annotations

from typing import Optional

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor

from ml_training.models import ModelAlgorithm, TaskType
from ml_training.training.base import BaseTrainer


class CatBoostTrainer(BaseTrainer):
    algorithm = ModelAlgorithm.CATBOOST

    def fit(
        self, X_train: np.ndarray, y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
    ) -> None:
        # allow_writing_files=False: CatBoost otherwise writes a
        # catboost_info/ directory of training logs into the current
        # working directory on every fit() call - never appropriate
        # for a production training service.
        params = {
            "random_state": self.config.random_state, "verbose": False,
            "allow_writing_files": False, **self.hyperparameters,
        }
        self._model = (
            CatBoostClassifier(**params) if self.task_type == TaskType.CLASSIFICATION
            else CatBoostRegressor(**params)
        )

        fit_kwargs = {}
        if X_val is not None and y_val is not None:
            fit_kwargs["eval_set"] = (X_val, y_val)
            fit_kwargs["early_stopping_rounds"] = self.config.early_stopping_rounds
            fit_kwargs["verbose"] = False

        self._model.fit(X_train, y_train, **fit_kwargs)
