"""
OptiTrade Model Serving Platform — top-level facade.

`PredictionService` (requirement 5) ties every piece together:
loading models (`loader.py`), inference (`inference.py`), calibration
(preferred automatically whenever `loader.py` finds one -
`LoadedModel.prediction_source`), metadata (`models.py:
PredictionMetadata`), and explanation inputs (feature importance read
straight back from the Feature Store, exactly as `ml_training.
importance` already persisted it - never recomputed here).

`get_active_engines()` is what `pipeline/service.py` calls to fold
every currently-served DIRECTION model into the production Pipeline as
an ordinary voting engine (requirement 9) - reusing `decision_engine`'s
own output shape with zero new response schema (requirement 2).

Version routing (requirement 6): `predict()` normally serves whatever
`ModelLoader.resolve_active_entry` resolves as ACTIVE (a rollback
override, if any, takes precedence - see `rollback.py`); passing
`model_id_override` bypasses both, serving that exact model_id
regardless of its promotion_state. This is documented, not
authentication-enforced (this codebase has no per-caller ACL layer
anywhere), the same way `ml_training.registry`'s `approved_by` is a
convention, not a login check - intended for Research Lab callers only;
the live `/quant/*` endpoints never pass it.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.interfaces import VotingEngineProtocol
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from ml_training.models import LabelName, ModelRegistryEntry, PromotionState
from model_serving.cache import ModelMetadataCache
from model_serving.config import ModelServingConfig
from model_serving.health import HealthMonitor
from model_serving.inference import InferenceEngine
from model_serving.loader import ModelLoader
from model_serving.models import MLPredictionResult, PredictionMetadata, ServingHealthReport
from model_serving.rollback import RollbackService
from model_serving.shadow import ShadowInferenceService

logger = logging.getLogger(__name__)

_IMPORTANCE_PREFIXES = ("shap_importance:", "permutation_importance:")


class PredictionService:
    def __init__(
        self,
        loader: Optional[ModelLoader] = None,
        inference_engine: Optional[InferenceEngine] = None,
        shadow_service: Optional[ShadowInferenceService] = None,
        rollback_service: Optional[RollbackService] = None,
        health_monitor: Optional[HealthMonitor] = None,
        feature_store: Optional[FeatureStoreService] = None,
        config: Optional[ModelServingConfig] = None,
    ) -> None:
        self.config = config or ModelServingConfig.from_env()
        self.cache = ModelMetadataCache(config=self.config)
        self.loader = loader or ModelLoader(cache=self.cache, config=self.config)
        self.inference_engine = inference_engine or InferenceEngine(config=self.config)
        self.shadow_service = shadow_service or ShadowInferenceService(
            loader=self.loader, inference_engine=self.inference_engine, config=self.config,
        )
        self.rollback_service = rollback_service or RollbackService()
        self.health_monitor = health_monitor or HealthMonitor(loader=self.loader, cache=self.cache, config=self.config)
        self.feature_store = feature_store or get_default_feature_store_service()

    # ── Startup ──────────────────────────────────────────────────────────

    def warm_up(self) -> int:
        return self.loader.warm_up()

    # ── Prediction ───────────────────────────────────────────────────────

    def predict(
        self,
        symbol: str,
        label_name: LabelName = LabelName.DIRECTION,
        horizon_days: int = 1,
        model_id_override: Optional[str] = None,
    ) -> MLPredictionResult:
        started_at = time.perf_counter()
        if model_id_override is not None:
            loaded_model = self.loader.load_version_override(model_id_override)
        else:
            entry = self._resolve_serving_entry(label_name, horizon_days)
            loaded_model = self.loader.load(entry)

        vote = self.inference_engine.predict_one(loaded_model, symbol)
        duration_ms = (time.perf_counter() - started_at) * 1000
        self.health_monitor.record_latency(duration_ms)

        entry = loaded_model.entry
        result = MLPredictionResult(
            symbol=symbol, label_name=label_name, horizon_days=horizon_days, vote=vote,
            metadata=PredictionMetadata(
                model_id=entry.model_id, algorithm=entry.algorithm, engine_version=entry.engine_version,
                promotion_state=entry.promotion_state, is_calibrated=loaded_model.calibrated is not None,
                checksum=loaded_model.checksum, feature_count=len(entry.feature_list),
                version_override_used=model_id_override is not None, loaded_at=loaded_model.loaded_at,
            ),
            explanation_inputs=self._explanation_inputs(entry.model_id),
        )

        if model_id_override is None:
            # Only real (non-override) traffic feeds shadow evaluation -
            # a Research Lab caller repeatedly probing a specific
            # version for its own analysis must not pollute Continuous
            # Learning's shadow sample history.
            self.shadow_service.submit(symbol, label_name)

        log_event(
            logger, component="model_serving", module="model_serving.service", operation="predict",
            status=STATUS_SUCCESS, symbol=symbol, model_id=entry.model_id, label_name=label_name.value,
            horizon_days=horizon_days, execution_time_ms=duration_ms,
        )
        return result

    async def predict_async(
        self,
        symbol: str,
        label_name: LabelName = LabelName.DIRECTION,
        horizon_days: int = 1,
        model_id_override: Optional[str] = None,
    ) -> MLPredictionResult:
        return await asyncio.to_thread(self.predict, symbol, label_name, horizon_days, model_id_override)

    # ── Pipeline integration ─────────────────────────────────────────────

    def get_active_engines(self) -> List[VotingEngineProtocol]:
        """Every currently-served DIRECTION model (rollback overrides
        respected), wrapped as a voting engine - what
        `pipeline.service.PipelineService` folds into its own engine
        list on every run (requirement 9). A model failing to load is
        logged (by `loader.py`) and simply excluded, never raised -
        one broken model must never break live decisioning."""
        combos = {
            (entry.label_name, entry.horizon_days)
            for entry in self.loader.registry_service.list_by_state(PromotionState.ACTIVE, limit=500)
            if entry.label_name == LabelName.DIRECTION
        }
        engines: List[VotingEngineProtocol] = []
        for label_name, horizon_days in combos:
            try:
                entry = self._resolve_serving_entry(label_name, horizon_days)
                loaded_model = self.loader.load(entry)
            except Exception:
                continue
            engines.append(self.inference_engine.adapter_for(loaded_model))
        return engines

    def run_shadow_inference(self, symbol: str, label_name: LabelName = LabelName.DIRECTION) -> None:
        """Fire-and-forget - see `shadow.py`. Exposed here so
        `pipeline.service.PipelineService` doesn't need its own
        reference to `ShadowInferenceService`."""
        self.shadow_service.submit(symbol, label_name)

    # ── Rollback ─────────────────────────────────────────────────────────

    def rollback_to(self, label_name: LabelName, horizon_days: int, model_id: str, rolled_back_by: str) -> None:
        self.rollback_service.rollback_to(label_name, horizon_days, model_id, rolled_back_by)
        self.cache.invalidate(label_name, horizon_days)
        log_event(
            logger, component="model_serving", module="model_serving.service", operation="rollback_to",
            status=STATUS_SUCCESS, label_name=label_name.value, horizon_days=horizon_days, model_id=model_id,
            rolled_back_by=rolled_back_by,
        )

    def clear_rollback(self, label_name: LabelName, horizon_days: int) -> None:
        self.rollback_service.clear_rollback(label_name, horizon_days)
        self.cache.invalidate(label_name, horizon_days)

    # ── Health ───────────────────────────────────────────────────────────

    def health_report(self) -> ServingHealthReport:
        return self.health_monitor.report()

    # ── Internals ────────────────────────────────────────────────────────

    def _resolve_serving_entry(self, label_name: LabelName, horizon_days: int) -> ModelRegistryEntry:
        override_entry = self.rollback_service.current_override(label_name, horizon_days)
        if override_entry is not None:
            return override_entry
        return self.loader.resolve_active_entry(label_name, horizon_days)

    def _explanation_inputs(self, model_id: str) -> Dict[str, float]:
        try:
            feature_names = self.feature_store.list_feature_names(model_id)
        except Exception as exc:
            log_event(
                logger, component="model_serving", module="model_serving.service", operation="explanation_inputs",
                status=STATUS_ERROR, model_id=model_id, error_type=type(exc).__name__, level=logging.WARNING,
            )
            return {}

        inputs: Dict[str, float] = {}
        for name in feature_names:
            if not name.startswith(_IMPORTANCE_PREFIXES):
                continue
            record = self.feature_store.get_latest_feature(model_id, name)
            if record is not None:
                inputs[name] = record.value
        return inputs
