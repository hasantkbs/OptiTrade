"""OptiTrade Model Serving Platform — exception types."""
from __future__ import annotations


class ModelServingError(Exception):
    """Base class for all Model Serving Platform errors."""


class NoActiveModelError(ModelServingError):
    """Raised when no ACTIVE model exists for the requested
    (label_name, horizon_days) and no rollback/version override applies."""


class ModelVersionNotFoundError(ModelServingError):
    """Raised when a specific `model_id` (rollback target, or a Research
    Lab version override) does not exist in the Model Registry."""


class ChecksumMismatchError(ModelServingError):
    """Raised when a loaded artifact's checksum does not match the
    checksum recorded the first time that exact model_id was loaded -
    signals on-disk corruption or an unexpected artifact swap."""


class InvalidModelMetadataError(ModelServingError):
    """Raised when a Model Registry entry or its loaded artifact fails
    metadata validation (missing feature list, empty artifact, not
    actually fitted, ...)."""


class InvalidRollbackError(ModelServingError):
    """Raised when a rollback is attempted without a human approver, or
    to a model_id that isn't a valid, existing registry entry."""


class InsufficientFeatureDataError(ModelServingError):
    """Raised when too few of a model's trained features are available
    in the live Feature Store for the requested symbol to trust a
    prediction (e.g. a symbol the Feature Store hasn't warmed up yet).
    Wraps `ml_training.exceptions.InsufficientFeatureCoverageError` -
    `model_serving` is the only production package allowed to import
    `ml_training` (see tests/test_research_isolation.py), so this gives
    `main.py` a `ModelServingError` subclass to catch without importing
    `ml_training` itself."""
