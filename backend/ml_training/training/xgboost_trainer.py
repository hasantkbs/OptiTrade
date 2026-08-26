"""OptiTrade ML Training Platform — XGBoost trainer."""
from __future__ import annotations

from typing import Optional

import numpy as np
import xgboost as xgb

from ml_training.models import ModelAlgorithm, TaskType
from ml_training.training.base import BaseTrainer


class XGBoostTrainer(BaseTrainer):
    algorithm = ModelAlgorithm.XGBOOST

    def fit(
        self, X_train: np.ndarray, y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
    ) -> None:
        y_train_encoded = self._encode_y(y_train, fit_encoder=True)

        params = {"random_state": self.config.random_state, **self.hyperparameters}
        if X_val is not None and y_val is not None:
            params["early_stopping_rounds"] = self.config.early_stopping_rounds
            if self.task_type == TaskType.CLASSIFICATION:
                # XGBoost's default eval_metric only works for binary
                # classification - a 3+-class problem (e.g. this
                # platform's own BUY/HOLD/SELL direction label) needs
                # mlogloss explicitly, discovered via real training on
                # exactly that label.
                n_classes = len(np.unique(y_train_encoded))
                params.setdefault("eval_metric", "logloss" if n_classes <= 2 else "mlogloss")

        self._model = (
            xgb.XGBClassifier(**params) if self.task_type == TaskType.CLASSIFICATION
            else xgb.XGBRegressor(**params)
        )

        fit_kwargs = {}
        if X_val is not None and y_val is not None:
            fit_kwargs["eval_set"] = [(X_val, self._encode_y(y_val, fit_encoder=False))]
            fit_kwargs["verbose"] = False

        self._model.fit(X_train, y_train_encoded, **fit_kwargs)
