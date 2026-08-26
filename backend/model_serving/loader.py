"""
OptiTrade Model Serving Platform — Model Loader.

Loads ACTIVE models directly from `ml_training.registry` (requirement
1):

  - lazy loading: nothing is loaded until first requested via
    `resolve_active_entry`/`load`.
  - warm startup: `warm_up()` eagerly loads every currently-ACTIVE
    model, intended to run once at process startup (see `service.py`).
  - automatic reload: every `resolve_active_entry` call re-checks the
    Model Cache (bounded staleness of `cache_ttl_seconds`) and, when the
    resolved model_id or its `promoted_at` has changed, transparently
    loads the new one on next `load()` - no restart required.
  - checksum verification: a sha256 of the artifact file is computed on
    first load and remembered for that model_id's whole process
    lifetime (independent of whether the trainer itself later gets
    evicted from the in-process cache); any later re-load of that exact
    model_id (`force_reload`, e.g. after `evict`) recomputes the
    checksum and raises `ChecksumMismatchError` if the bytes on disk no
    longer match - `ml_training.registry` has no checksum column of its
    own (nothing else in this platform needs one), so this is trust-on-
    first-use, exactly like an SSH host key.
  - metadata validation: the registry entry (non-empty feature list,
    artifact file actually present) and the loaded trainer itself (a
    populated `classes_`, proving the artifact is a genuinely-fitted
    classifier and not an empty/corrupted file) are both checked before
    a model is accepted into the cache.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

import joblib

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from ml_training.calibration.repository import CalibrationRepository
from ml_training.models import LabelName, ModelRegistryEntry, PromotionState, TaskType
from ml_training.registry.service import ModelRegistryService
from ml_training.training.base import BaseTrainer
from ml_training.training.service import create_trainer
from model_serving.cache import ModelMetadataCache
from model_serving.config import ModelServingConfig
from model_serving.exceptions import (
    ChecksumMismatchError,
    InvalidModelMetadataError,
    ModelVersionNotFoundError,
    NoActiveModelError,
)

logger = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    """One in-process-loaded model: the registry entry, its raw
    trainer, an optional calibrated wrapper (preferred for inference
    when present - see `ml_training.calibration.calibrator.
    _CalibratedTrainerAdapter`), and this loader's own bookkeeping."""

    entry: ModelRegistryEntry
    trainer: BaseTrainer
    calibrated: Optional[object]
    checksum: str
    loaded_at: datetime

    @property
    def prediction_source(self):
        """Whichever of `calibrated`/`trainer` should actually be used
        for `predict`/`predict_proba`/`classes_` - the calibrated
        wrapper is preferred whenever one exists, since it has
        strictly better-calibrated probabilities."""
        return self.calibrated if self.calibrated is not None else self.trainer


def compute_checksum(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModelLoader:
    def __init__(
        self,
        registry_service: Optional[ModelRegistryService] = None,
        calibration_repository: Optional[CalibrationRepository] = None,
        cache: Optional[ModelMetadataCache] = None,
        config: Optional[ModelServingConfig] = None,
    ) -> None:
        self.config = config or ModelServingConfig.from_env()
        self.registry_service = registry_service or ModelRegistryService()
        self.calibration_repository = calibration_repository or CalibrationRepository()
        self.cache = cache or ModelMetadataCache(config=self.config)
        # Ordered oldest-accessed-first -> most-recently-accessed-last, so
        # capacity eviction (`_enforce_capacity`) always drops the least
        # recently used entry. `_known_checksums` is intentionally a
        # separate, unbounded dict (see its docstring note above) - it is
        # tiny (one string per model_id ever loaded) and evicting it would
        # defeat the tamper/corruption check `force_reload` relies on.
        self._loaded: "OrderedDict[str, LoadedModel]" = OrderedDict()
        self._known_checksums: Dict[str, str] = {}
        self._last_load_error: Dict[str, str] = {}
        self.loading_failure_count = 0

    # ── Version routing ─────────────────────────────────────────────────

    def resolve_active_entry(self, label_name: LabelName, horizon_days: int) -> ModelRegistryEntry:
        """The currently ACTIVE registry entry for (label_name,
        horizon_days) - served from the Model Cache when present,
        otherwise resolved straight from `ml_training.registry` and
        cached for next time. Raises `NoActiveModelError` if nothing is
        ACTIVE for this combination."""
        cached = self.cache.get_active_entry(label_name, horizon_days)
        if cached is not None:
            return cached

        entry = self._resolve_active_entry_from_registry(label_name, horizon_days)
        self.cache.set_active_entry(label_name, horizon_days, entry)
        return entry

    def _resolve_active_entry_from_registry(self, label_name: LabelName, horizon_days: int) -> ModelRegistryEntry:
        active_entries = [
            entry for entry in self.registry_service.list_by_state(PromotionState.ACTIVE, limit=500)
            if entry.label_name == label_name and entry.horizon_days == horizon_days
        ]
        if not active_entries:
            raise NoActiveModelError(
                f"no ACTIVE model registered for label_name={label_name.value!r}, horizon_days={horizon_days}"
            )
        # Exactly one ACTIVE model per (label_name, horizon_days) is the
        # expected steady state - if more than one is somehow ACTIVE at
        # once, the most recently promoted one is served rather than
        # raising, since availability matters more than flagging an
        # inconsistency the registry itself should have prevented.
        active_entries.sort(key=lambda entry: entry.promoted_at or entry.training_date, reverse=True)
        return active_entries[0]

    def load_version_override(self, model_id: str) -> LoadedModel:
        """Loads an arbitrary registered model_id regardless of its
        promotion_state - the path a Research Lab caller (or a
        rollback) uses to bypass "must be ACTIVE". See
        `service.py:PredictionService.predict`'s `model_id_override`
        parameter, documented there as Research-Lab-only."""
        entry = self.registry_service.get(model_id)
        if entry is None:
            raise ModelVersionNotFoundError(f"no registered model with model_id {model_id!r}")
        return self.load(entry)

    # ── Loading ──────────────────────────────────────────────────────────

    def load(self, entry: ModelRegistryEntry) -> LoadedModel:
        """Lazily loads (or returns the already in-process-loaded)
        trainer for `entry.model_id`."""
        existing = self._loaded.get(entry.model_id)
        if existing is not None and existing.entry.promoted_at == entry.promoted_at:
            self._loaded.move_to_end(entry.model_id)
            return existing

        self._validate_entry_metadata(entry)

        started_at = time.perf_counter()
        try:
            checksum = compute_checksum(entry.artifact_path)
            previously_known = self._known_checksums.get(entry.model_id)
            if previously_known is not None and previously_known != checksum:
                raise ChecksumMismatchError(
                    f"model {entry.model_id!r}: artifact checksum changed since it was first loaded "
                    f"(expected {previously_known}, got {checksum}) - possible corruption or tampering"
                )

            trainer = create_trainer(entry.algorithm, TaskType.CLASSIFICATION, entry.feature_list)
            trainer.load(entry.artifact_path)
            self._validate_loaded_trainer(entry, trainer)

            calibrated = self._load_calibrated(entry.model_id)
        except Exception as exc:
            self.loading_failure_count += 1
            self._last_load_error[entry.model_id] = f"{type(exc).__name__}: {exc}"
            log_event(
                logger, component="model_serving", module="model_serving.loader", operation="load",
                status=STATUS_ERROR, model_id=entry.model_id, error_type=type(exc).__name__, level=logging.ERROR,
            )
            raise

        self._known_checksums[entry.model_id] = checksum
        loaded = LoadedModel(
            entry=entry, trainer=trainer, calibrated=calibrated, checksum=checksum,
            loaded_at=datetime.now(timezone.utc),
        )
        self._loaded[entry.model_id] = loaded
        self._loaded.move_to_end(entry.model_id)
        self._enforce_capacity()
        log_event(
            logger, component="model_serving", module="model_serving.loader", operation="load",
            status=STATUS_SUCCESS, model_id=entry.model_id, algorithm=entry.algorithm.value,
            is_calibrated=calibrated is not None, execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return loaded

    def _enforce_capacity(self) -> None:
        """Evicts the least-recently-used model(s) once `_loaded` exceeds
        `config.loader_max_cached_models`. Only the in-process trainer is
        dropped (same as `evict()`) - the known checksum is kept, so a
        later reload of an evicted model_id still detects on-disk drift."""
        max_size = self.config.loader_max_cached_models
        while len(self._loaded) > max_size:
            evicted_model_id, _ = self._loaded.popitem(last=False)
            log_event(
                logger, component="model_serving", module="model_serving.loader", operation="evict_lru",
                status=STATUS_SUCCESS, model_id=evicted_model_id, cache_size=len(self._loaded), max_size=max_size,
            )

    def warm_up(self) -> int:
        """Eagerly loads every currently-ACTIVE model. A single model
        failing to load is logged (via `load()`) and skipped - one
        broken model must never prevent every other model, or the
        process itself, from starting."""
        loaded_count = 0
        for entry in self.registry_service.list_by_state(PromotionState.ACTIVE, limit=500):
            try:
                self.load(entry)
                loaded_count += 1
            except Exception:
                continue
        log_event(
            logger, component="model_serving", module="model_serving.loader", operation="warm_up",
            status=STATUS_SUCCESS, loaded_count=loaded_count,
        )
        return loaded_count

    def evict(self, model_id: str) -> None:
        """Removes a model from the in-process cache without
        forgetting its known checksum - a later `force_reload` still
        detects on-disk drift."""
        self._loaded.pop(model_id, None)

    def force_reload(self, model_id: str) -> LoadedModel:
        self.evict(model_id)
        return self.load_version_override(model_id)

    def loaded_models(self) -> Dict[str, LoadedModel]:
        return dict(self._loaded)

    def last_load_error(self, model_id: str) -> Optional[str]:
        return self._last_load_error.get(model_id)

    # ── Internals ────────────────────────────────────────────────────────

    def _load_calibrated(self, model_id: str) -> Optional[object]:
        result = self.calibration_repository.get_latest(model_id)
        if result is None:
            return None
        return joblib.load(result.artifact_path)

    @staticmethod
    def _validate_entry_metadata(entry: ModelRegistryEntry) -> None:
        if not entry.feature_list:
            raise InvalidModelMetadataError(f"model {entry.model_id!r} has an empty feature_list")
        if not os.path.exists(entry.artifact_path):
            raise InvalidModelMetadataError(
                f"model {entry.model_id!r}: artifact_path {entry.artifact_path!r} does not exist"
            )

    @staticmethod
    def _validate_loaded_trainer(entry: ModelRegistryEntry, trainer: BaseTrainer) -> None:
        if not trainer.is_fitted:
            raise InvalidModelMetadataError(f"model {entry.model_id!r}: loaded artifact is not a fitted trainer")
        if trainer.classes_ is None or len(trainer.classes_) < 2:
            raise InvalidModelMetadataError(
                f"model {entry.model_id!r}: loaded trainer has fewer than two classes - not usable for serving"
            )
