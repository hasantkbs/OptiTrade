"""OptiTrade ML Training Platform — calibration service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import joblib
import numpy as np

from core.structured_logging import STATUS_SKIPPED, STATUS_SUCCESS, log_event
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
        was_skipped = calibrated_model is trainer
        if was_skipped:
            logger.warning(
                "calibrate_and_save: calibration was skipped for model_id=%s (method=%s) - "
                "the calibration split was missing a known class, so ModelCalibrator.calibrate "
                "returned the trainer unmodified. The CalibrationResult below is NOT persisted "
                "to the repository (unlike a real calibration run) precisely because "
                "calibration_error_before == calibration_error_after here does NOT mean "
                "calibration had no effect - it means no calibration ran at all, and a "
                "persisted row would be indistinguishable from a successful run.",
                model_id, method.value,
            )
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
        # A skipped calibration must NOT persist a DB row indistinguishable
        # from a successful run - the only caller (ml_training/service.py)
        # discards this method's return value, so `result` is still built
        # and returned in case a future caller wants it in-memory, but it
        # is never saved to the repository when skipped (Finding 4).
        if not was_skipped:
            self.repository.save(result)

        log_event(
            logger, component="ml_training", module="ml_training.calibration.service",
            operation="calibrate_and_save", status=STATUS_SKIPPED if was_skipped else STATUS_SUCCESS,
            model_id=model_id, method=method.value,
            calibration_error_before=error_before, calibration_error_after=error_after,
        )
        return result

    def get_latest(self, model_id: str) -> Optional[CalibrationResult]:
        return self.repository.get_latest(model_id)

    def list_for_model(self, model_id: str, limit: int = 20) -> List[CalibrationResult]:
        return self.repository.list_for_model(model_id, limit)
