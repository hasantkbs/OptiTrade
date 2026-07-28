"""OptiTrade ML Training Platform — calibration service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import joblib
import numpy as np

from core.structured_logging import STATUS_SUCCESS, log_event
from ml_training.calibration.calibrator import ModelCalibrator
from ml_training.calibration.repository import CalibrationRepository
from ml_training.config import MLTrainingConfig
from ml_training.evaluation.metrics import calibration_error_from_predictions
from ml_training.models import CalibrationMethod, CalibrationResult
from ml_training.training.base import BaseTrainer

logger = logging.getLogger(__name__)


class CalibrationService:
    """Calibrates a trainer's predicted probabilities and persists both
    the calibrated model artifact and the before/after calibration
    error."""

    def __init__(
        self,
        calibrator: Optional[ModelCalibrator] = None,
        repository: Optional[CalibrationRepository] = None,
        config: Optional[MLTrainingConfig] = None,
    ) -> None:
        self.config = config or MLTrainingConfig.from_env()
        self.calibrator = calibrator or ModelCalibrator(config=self.config)
        self.repository = repository or CalibrationRepository()

    def calibrate_and_save(
        self,
        model_id: str,
        trainer: BaseTrainer,
        X_cal: np.ndarray, y_cal: np.ndarray,
        X_test: np.ndarray, y_test: np.ndarray,
        method: CalibrationMethod,
        artifact_path: str,
    ) -> CalibrationResult:
        error_before = calibration_error_from_predictions(
            y_test, trainer.predict(X_test), trainer.predict_proba(X_test), self.config.calibration_bins,
        )

        calibrated_model = self.calibrator.calibrate(trainer, X_cal, y_cal, method)
        error_after = calibration_error_from_predictions(
            y_test, calibrated_model.predict(X_test), calibrated_model.predict_proba(X_test),
            self.config.calibration_bins,
        )

        joblib.dump(calibrated_model, artifact_path)

        result = CalibrationResult(
            model_id=model_id, method=method, calibration_error_before=error_before,
            calibration_error_after=error_after, artifact_path=artifact_path,
            computed_at=datetime.now(timezone.utc),
        )
        self.repository.save(result)

        log_event(
            logger, component="ml_training", module="ml_training.calibration.service",
            operation="calibrate_and_save", status=STATUS_SUCCESS, model_id=model_id, method=method.value,
            calibration_error_before=error_before, calibration_error_after=error_after,
        )
        return result

    def get_latest(self, model_id: str) -> Optional[CalibrationResult]:
        return self.repository.get_latest(model_id)

    def list_for_model(self, model_id: str, limit: int = 20) -> List[CalibrationResult]:
        return self.repository.list_for_model(model_id, limit)
