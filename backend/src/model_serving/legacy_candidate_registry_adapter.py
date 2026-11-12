"""
OptiTrade Model Serving Platform — legacy XGBoost candidate registration.

Bridges Task 0.2-A's versioned candidate-artifact writing
(`research.ml_trainer.write_candidate_artifact`) into the Model Registry
(`ml_training.registry`) as a CANDIDATE row - nothing more. This module
is the one place `main.py`'s self_evolution_loop is allowed to reach
`ml_training` from: `model_serving/__init__.py`'s own docstring states
"only model_serving itself may depend on ml_training", and
`tests/test_research_isolation.py` enforces it. It must therefore never
import `research`/`research_lab` (that same test scans every file
directly under `model_serving/` for exactly this), and it accepts only
primitive arguments (`candidate_id`/`artifact_path`/`created_at`),
never `research.ml_trainer.CandidateArtifact` itself - `main.py` (which
already imports `research.ml_trainer.train`) is the one place that
unpacks that object before calling here.

This module NEVER promotes, activates, or shadow-deploys a model - it
only ever calls `ModelRegistryService.register()`, which itself refuses
anything but `PromotionState.CANDIDATE` (see
`ml_training/registry/service.py:register`).

Metadata mapping (CTO-approved, Task 0.2-B):
    model_id        = f"legacy_xgb_signal_{candidate_id}" - new
                       convention, candidate_id is already unique and
                       stable across retries (Task 0.2-A).
    engine_name     = f"MLModel:{model_id}" - NOT invented for this
                       task: the exact, pre-existing convention
                       `ml_training/shadow/adapter.py`'s
                       `MLModelVotingEngineAdapter` already derives for
                       every model-backed voting engine, confirmed
                       against that file and its own test fixtures
                       (`tests/test_model_serving_shadow.py`,
                       `tests/test_ml_training_shadow.py`).
    engine_version  = candidate_id
    version         = candidate_id
    algorithm       = ModelAlgorithm.XGBOOST
    label_name      = LabelName.DIRECTION
    horizon_days    = package["forward_days"]
    training_date   = created_at
    feature_list    = package["feature_names"]
    artifact_path   = artifact_path
    hyperparameters = the NUMERIC SUBSET of the real, fitted model's
                       own `get_params()` - see
                       `_extract_numeric_hyperparameters`'s own
                       docstring for why the raw dict cannot be used
                       directly (confirmed empirically: it fails 28
                       Pydantic validations against this schema's
                       `Dict[str, float]`).
    metrics.accuracy = package["cv_accuracy_mean"] - the only
                       `ModelMetrics` field this family ever truthfully
                       computes. Every other field (precision, recall,
                       f1, roc_auc, sharpe_ratio, ...) is left at its
                       Pydantic default - never fabricated.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime
from typing import Dict, Optional

import joblib

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from ml_training.exceptions import MLTrainingPersistenceError
from ml_training.models import LabelName, ModelAlgorithm, ModelMetrics, ModelRegistryEntry
from ml_training.registry.service import ModelRegistryService
from model_serving.exceptions import (
    CandidateArtifactUnreadableError,
    CandidateRegistrationConflictError,
    CandidateRegistrationError,
)

logger = logging.getLogger(__name__)

_MODEL_ID_PREFIX = "legacy_xgb_signal_"


def _model_id_for(candidate_id: str) -> str:
    return f"{_MODEL_ID_PREFIX}{candidate_id}"


def _extract_numeric_hyperparameters(fitted_model) -> Dict[str, float]:
    """`fitted_model.get_params()` (a real, fitted XGBClassifier) returns
    ~39 keys of mixed types - strings (e.g. `eval_metric="logloss"`),
    `None` (most unset constructor args), bools, and numbers - verified
    empirically before writing this function: passing that raw dict
    straight into `ModelRegistryEntry(hyperparameters=...)` (typed
    `Dict[str, float]`) raises 28 Pydantic validation errors. This
    returns the truthful NUMERIC SUBSET only - every key kept is the
    model's own real, actually-used hyperparameter, never a fabricated
    value; keys are only ever dropped, never invented. `bool` is
    excluded even though Python's `bool` is an `int` subclass, since
    representing a flag like `enable_categorical=False` as `0.0` would
    misrepresent a boolean as a magnitude.

    Non-finite values (`NaN`, `+inf`, `-inf`) are also excluded - XGBoost's
    own `missing` parameter defaults to `nan` (its "treat NaN as missing"
    sentinel), which `float('nan')` would otherwise pass straight through
    as a technically-valid-but-meaningless `Dict[str, float]` entry. No
    replacement value is substituted for a dropped non-finite entry -
    the key is simply absent, exactly like every other dropped key."""
    raw_params = fitted_model.get_params()
    numeric_params: Dict[str, float] = {}
    for key, value in raw_params.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        value = float(value)
        if not math.isfinite(value):
            continue
        numeric_params[key] = value
    return numeric_params


def _validate_artifact_reference(candidate_id: str, artifact_path: str) -> None:
    """Cheap, local checks only - no file I/O beyond `os.path.exists` -
    run on every call, including an eventual idempotent-retry hit,
    before any registry round-trip."""
    if candidate_id not in os.path.basename(artifact_path):
        raise CandidateArtifactUnreadableError(
            f"candidate_id {candidate_id!r} does not appear in artifact filename "
            f"{os.path.basename(artifact_path)!r} - refusing to register a mismatched reference"
        )
    if not os.path.exists(artifact_path):
        raise CandidateArtifactUnreadableError(f"candidate artifact does not exist at {artifact_path!r}")


def _load_package(candidate_id: str, artifact_path: str) -> dict:
    try:
        return joblib.load(artifact_path)
    except Exception as exc:
        raise CandidateArtifactUnreadableError(
            f"candidate artifact at {artifact_path!r} (candidate_id={candidate_id!r}) could not be read: {exc}"
        ) from exc


def register_legacy_candidate(
    candidate_id: str,
    artifact_path: str,
    created_at: datetime,
    registry_service: Optional[ModelRegistryService] = None,
) -> ModelRegistryEntry:
    """Registers the legacy self-evolution XGBoost candidate written by
    `research.ml_trainer.write_candidate_artifact` into `ml_training.registry`
    as a CANDIDATE row - never SHADOW/ACTIVE, never promoted, never
    deployed (see this module's own docstring for the full metadata
    mapping).

    Idempotent for a genuine retry of the SAME candidate (same
    deterministic `model_id`, same `artifact_path`): returns the
    already-registered entry rather than erroring or re-reading the
    artifact. Raises `CandidateRegistrationConflictError` if that
    `model_id` already exists under a DIFFERENT `artifact_path` - a
    real naming collision, never silently resolved. Raises
    `CandidateArtifactUnreadableError` if the artifact is missing,
    unreadable, or its `candidate_id` doesn't match its own filename -
    checked before any registry call. Raises `CandidateRegistrationError`
    if the registry itself (Postgres) is unreachable or persistence
    otherwise fails - propagated, never swallowed; `self_evolution_loop`'s
    own existing error handling is what actually absorbs this.

    Never writes to, moves, or deletes anything at `artifact_path` - at
    most one read-only `joblib.load()`, only when a genuinely new
    registration is needed.

    Concurrent-registration recovery: the initial `get()` above and the
    `register()` call below are not atomic with each other (no row lock,
    no transaction spanning both - see Task 0.2-B's own CTO review for
    why this is a known, accepted limitation, not fixed by adding a
    lock here), so two calls for the SAME candidate can both observe
    "not yet registered" and both attempt `register()`. The database's
    own `model_id` UNIQUE constraint then makes the losing call's
    `register()` fail with `MLTrainingPersistenceError` - on that
    specific failure, exactly one recovery `get()` is performed before
    deciding how to report it: a matching `artifact_path` means the
    other call's registration is this same candidate (idempotent
    success); a different `artifact_path` is a genuine conflict; no row
    at all means the registry failure was real (e.g. a genuine outage),
    not a benign race, and is propagated as such."""
    registry_service = registry_service or ModelRegistryService()
    model_id = _model_id_for(candidate_id)

    _validate_artifact_reference(candidate_id, artifact_path)

    try:
        existing = registry_service.get(model_id)
    except MLTrainingPersistenceError as exc:
        log_event(
            logger, component="model_serving", module="model_serving.legacy_candidate_registry_adapter",
            operation="register_legacy_candidate", status=STATUS_ERROR,
            model_id=model_id, candidate_id=candidate_id, error_type=type(exc).__name__, level=logging.ERROR,
        )
        raise CandidateRegistrationError(str(exc)) from exc

    if existing is not None:
        if existing.artifact_path == artifact_path:
            log_event(
                logger, component="model_serving", module="model_serving.legacy_candidate_registry_adapter",
                operation="register_legacy_candidate", status=STATUS_SUCCESS,
                model_id=model_id, candidate_id=candidate_id, already_registered=True,
            )
            return existing
        raise CandidateRegistrationConflictError(
            f"model_id {model_id!r} is already registered with artifact_path "
            f"{existing.artifact_path!r}, which differs from the candidate being "
            f"registered now ({artifact_path!r}) - refusing to overwrite a conflicting record"
        )

    package = _load_package(candidate_id, artifact_path)

    entry = ModelRegistryEntry(
        model_id=model_id,
        algorithm=ModelAlgorithm.XGBOOST,
        version=candidate_id,
        hyperparameters=_extract_numeric_hyperparameters(package["model"]),
        metrics=ModelMetrics(accuracy=package["cv_accuracy_mean"]),
        feature_list=package["feature_names"],
        label_name=LabelName.DIRECTION,
        horizon_days=package["forward_days"],
        training_date=created_at,
        engine_name=f"MLModel:{model_id}",
        engine_version=candidate_id,
        artifact_path=artifact_path,
    )

    try:
        registered = registry_service.register(entry)
    except MLTrainingPersistenceError as exc:
        log_event(
            logger, component="model_serving", module="model_serving.legacy_candidate_registry_adapter",
            operation="register_legacy_candidate", status=STATUS_ERROR,
            model_id=model_id, candidate_id=candidate_id, error_type=type(exc).__name__, level=logging.ERROR,
        )

        try:
            recovered = registry_service.get(model_id)
        except MLTrainingPersistenceError as recovery_exc:
            log_event(
                logger, component="model_serving", module="model_serving.legacy_candidate_registry_adapter",
                operation="register_legacy_candidate_recovery", status=STATUS_ERROR,
                model_id=model_id, candidate_id=candidate_id,
                error_type=type(recovery_exc).__name__, level=logging.ERROR,
            )
            raise CandidateRegistrationError(str(recovery_exc)) from recovery_exc

        if recovered is not None:
            if recovered.artifact_path == artifact_path:
                log_event(
                    logger, component="model_serving", module="model_serving.legacy_candidate_registry_adapter",
                    operation="register_legacy_candidate", status=STATUS_SUCCESS,
                    model_id=model_id, candidate_id=candidate_id,
                    already_registered=True, recovered_from_concurrent_race=True,
                )
                return recovered
            raise CandidateRegistrationConflictError(
                f"model_id {model_id!r} is already registered with artifact_path "
                f"{recovered.artifact_path!r} (discovered via post-failure recovery lookup), "
                f"which differs from the candidate being registered now "
                f"({artifact_path!r}) - refusing to overwrite a conflicting record"
            ) from exc

        # No row exists even after the recovery lookup - the original
        # register() failure was real (e.g. a genuine outage), not a
        # benign concurrent-registration race. Report it as such.
        raise CandidateRegistrationError(str(exc)) from exc

    log_event(
        logger, component="model_serving", module="model_serving.legacy_candidate_registry_adapter",
        operation="register_legacy_candidate", status=STATUS_SUCCESS,
        model_id=model_id, candidate_id=candidate_id, already_registered=False,
    )
    return registered
