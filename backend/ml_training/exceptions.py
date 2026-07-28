"""OptiTrade ML Training Platform — exception types."""
from __future__ import annotations


class MLTrainingError(Exception):
    """Base class for all ML Training Platform errors."""


class MLTrainingPersistenceError(MLTrainingError):
    """Raised when an ML Training Platform artifact could not be read
    from or written to storage."""


class InsufficientDataError(MLTrainingError):
    """Raised when a dataset has too few samples to train or evaluate
    meaningfully."""


class ModelNotFittedError(MLTrainingError):
    """Raised when predict()/predict_proba()/feature_importance() is
    called on a trainer that has not been fit yet."""


class UnknownAlgorithmError(MLTrainingError):
    """Raised when a requested algorithm name has no registered
    trainer."""


class InvalidPromotionError(MLTrainingError):
    """Raised when a model registry promotion transition is not
    allowed, or is attempted without a human approver."""
