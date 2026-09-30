"""
OptiTrade ML Training Platform — Calibration.

Isotonic Regression and Platt Scaling via
`sklearn.calibration.CalibratedClassifierCV`, wrapping the already-
fitted trainer via `sklearn.frozen.FrozenEstimator`. Persists the
calibrated model.
"""
from ml_training.calibration.service import CalibrationService

__all__ = ["CalibrationService"]
