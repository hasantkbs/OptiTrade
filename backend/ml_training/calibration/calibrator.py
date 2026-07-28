"""
OptiTrade ML Training Platform — probability calibration.

Reuses `sklearn.calibration.CalibratedClassifierCV` directly for both
Isotonic Regression and Platt Scaling (`method="sigmoid"` in
scikit-learn's own terminology) - never hand-rolls either algorithm.
Wraps the already-fitted trainer with `sklearn.frozen.FrozenEstimator`
(scikit-learn >= 1.6's replacement for the removed `cv="prefit"`) so
calibration fits only the calibration mapping itself on a held-out
calibration split, never re-fitting the underlying model.

`trainer._model` was fit on `BaseTrainer._encode_y`'s encoded integer
labels (necessary for XGBoost, which rejects non-numeric labels
outright - see `training/base.py`), so `FrozenEstimator(trainer._model)
.classes_` is already in that encoded-int space. `y_cal` must therefore
be encoded the same way before `CalibratedClassifierCV.fit()`, or its
own internal label encoder (fit on whatever space `y_cal` arrives in)
mismatches the frozen estimator's and calibration silently breaks (or
raises "y contains previously unseen labels" the moment `y_cal` isn't
already 0..n-1 integers, which is exactly what happens for this
platform's own BUY/HOLD/SELL direction labels). `_CalibratedTrainerAdapter`
decodes back to the trainer's original label space on the way out, so
from a caller's perspective a calibrated model's `predict()` returns the
exact same label values the underlying trainer's `predict()` would.
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


class _CalibratedTrainerAdapter:
    """Wraps a `CalibratedClassifierCV` fit in a trainer's encoded-int
    label space so `predict()` returns the trainer's own original
    label values - the same contract every trainer in this platform
    already exposes."""

    def __init__(self, calibrated_model: CalibratedClassifierCV, label_encoder) -> None:
        self._calibrated_model = calibrated_model
        self._label_encoder = label_encoder

    def predict(self, X: np.ndarray) -> np.ndarray:
        raw = np.asarray(self._calibrated_model.predict(X))
        return self._label_encoder.inverse_transform(raw.astype(int))

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._calibrated_model.predict_proba(X)


class ModelCalibrator:
    def __init__(self, config: Optional[MLTrainingConfig] = None) -> None:
        self.config = config or MLTrainingConfig.from_env()

    def calibrate(
        self, trainer: BaseTrainer, X_cal: np.ndarray, y_cal: np.ndarray, method: CalibrationMethod,
    ) -> _CalibratedTrainerAdapter:
        if trainer.task_type != TaskType.CLASSIFICATION:
            raise ValueError(
                f"{trainer.algorithm.value}: calibration only applies to classification models, "
                f"this trainer's task_type is {trainer.task_type.value}"
            )
        if not trainer.is_fitted:
            raise ValueError(f"{trainer.algorithm.value}: trainer must be fit before it can be calibrated")

        y_cal_encoded = trainer._encode_y(y_cal, fit_encoder=False)

        # CalibratedClassifierCV still internally cross-validates even
        # with a frozen (never-refit) estimator - it only skips
        # re-fitting the estimator itself, not the fold splitting used
        # to fit the calibration curve. Its default of 5 stratified
        # folds fails outright on a small calibration split where some
        # class has fewer than 5 members, which is routine for a
        # modest training run - so `cv` is capped at the rarest
        # observed class's count instead of always defaulting to 5.
        _, class_counts = np.unique(y_cal_encoded, return_counts=True)
        cv = max(2, min(5, int(class_counts.min())))

        frozen_estimator = FrozenEstimator(trainer._model)
        calibrated_model = CalibratedClassifierCV(frozen_estimator, method=_SKLEARN_METHOD[method], cv=cv)
        calibrated_model.fit(X_cal, y_cal_encoded)
        return _CalibratedTrainerAdapter(calibrated_model, trainer._label_encoder)
