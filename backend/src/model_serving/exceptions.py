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


class CandidateArtifactUnreadableError(ModelServingError):
    """Raised by `legacy_candidate_registry_adapter.register_legacy_candidate`
    when a candidate artifact is missing, cannot be parsed by joblib, or
    its candidate_id does not appear in its own filename - checked
    BEFORE any registry call, so a bad or mismatched reference never
    reaches the database."""


class CandidateRegistrationConflictError(ModelServingError):
    """Raised when a candidate's deterministic model_id already exists
    in the registry under a DIFFERENT artifact_path - a genuine naming
    collision between two different artifacts. Never silently resolved
    as success; distinct from a true retry of the same candidate (same
    model_id AND same artifact_path), which IS treated as idempotent."""


class CandidateRegistrationError(ModelServingError):
    """Wraps `ml_training.exceptions.MLTrainingPersistenceError` - raised
    when the Model Registry itself (Postgres) could not be reached or a
    write failed for a reason other than the idempotent-duplicate or
    conflict cases above. Propagated, never swallowed - `model_serving`
    is the only production package allowed to import `ml_training` (see
    tests/test_research_isolation.py), so this gives callers like
    `main.py` a `ModelServingError` subclass to catch without importing
    `ml_training` itself, matching `InsufficientFeatureDataError`'s own
    existing wrapping convention below."""


class InsufficientFeatureDataError(ModelServingError):
    """Raised when too few of a model's trained features are available
    in the live Feature Store for the requested symbol to trust a
    prediction (e.g. a symbol the Feature Store hasn't warmed up yet).
    Wraps `ml_training.exceptions.InsufficientFeatureCoverageError` -
    `model_serving` is the only production package allowed to import
    `ml_training` (see tests/test_research_isolation.py), so this gives
    `main.py` a `ModelServingError` subclass to catch without importing
    `ml_training` itself."""
