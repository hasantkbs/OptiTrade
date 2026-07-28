"""
OptiTrade ML Training Platform — probability calibration.

Reuses `sklearn.calibration.CalibratedClassifierCV` directly for both
Isotonic Regression and Platt Scaling (`method="sigmoid"` in
scikit-learn's own terminology) - never hand-rolls either algorithm.
Wraps the already-fitted trainer with `sklearn.frozen.FrozenEstimator`
(scikit-learn >= 1.6's replacement for the removed `cv="prefit"`) so
calibration fits only the calibration mapping itself on a held-out
calibration split, never re-fitting the underlying model.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator

from ml_training.config import MLTrainingConfig
from ml_training.models import CalibrationMethod, TaskType
from ml_training.training.base import BaseTrainer

_SKLEARN_METHOD = {
    CalibrationMethod.ISOTONIC: "isotonic",
    CalibrationMethod.PLATT: "sigmoid",
}


class ModelCalibrator:
    def __init__(self, config: Optional[MLTrainingConfig] = None) -> None:
        self.config = config or MLTrainingConfig.from_env()

    def calibrate(
        self, trainer: BaseTrainer, X_cal: np.ndarray, y_cal: np.ndarray, method: CalibrationMethod,
    ) -> CalibratedClassifierCV:
        if trainer.task_type != TaskType.CLASSIFICATION:
            raise ValueError(
                f"{trainer.algorithm.value}: calibration only applies to classification models, "
                f"this trainer's task_type is {trainer.task_type.value}"
            )
        if not trainer.is_fitted:
            raise ValueError(f"{trainer.algorithm.value}: trainer must be fit before it can be calibrated")

        frozen_estimator = FrozenEstimator(trainer._model)
        calibrated_model = CalibratedClassifierCV(frozen_estimator, method=_SKLEARN_METHOD[method])
        calibrated_model.fit(X_cal, y_cal)
        return calibrated_model
