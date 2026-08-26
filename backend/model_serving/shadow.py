"""
OptiTrade Model Serving Platform — Shadow Inference.

Runs every currently-SHADOW model against the same live traffic a
served ACTIVE prediction just handled, entirely outside the response
the caller receives - exactly the same "shadow mode never affects a
live decision" guarantee `ml_training.shadow`/`research_lab.shadow`
already establish, just triggered inline per live prediction rather
than as a periodic batch pass. Every shadow vote is fed straight into
`learning.service.LearningService.record_shadow_vote` - the same
Continuous Learning tracking path a shadow-deployed model already uses
- so only Continuous Learning (and, downstream, Research Lab reading
Continuous Learning's own tables) ever consumes a shadow prediction.
Nothing here returns a shadow vote to any caller.

`submit` is fire-and-forget by design: it hands the work to a small
background thread pool and returns immediately, so a live prediction's
latency is never affected by how many shadow models exist or how long
they take. Any failure evaluating a shadow model is logged and
swallowed - by definition, nothing outside Continuous Learning is
watching for it.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from learning.service import LearningService
from ml_training.models import LabelName, PromotionState
from ml_training.registry.service import ModelRegistryService
from model_serving.config import ModelServingConfig
from model_serving.inference import InferenceEngine
from model_serving.loader import ModelLoader

logger = logging.getLogger(__name__)


class ShadowInferenceService:
    def __init__(
        self,
        loader: Optional[ModelLoader] = None,
        inference_engine: Optional[InferenceEngine] = None,
        registry_service: Optional[ModelRegistryService] = None,
        learning_service: Optional[LearningService] = None,
        config: Optional[ModelServingConfig] = None,
    ) -> None:
        self.config = config or ModelServingConfig.from_env()
        self.loader = loader or ModelLoader(config=self.config)
        self.inference_engine = inference_engine or InferenceEngine(config=self.config)
        self.registry_service = registry_service or ModelRegistryService()
        self.learning_service = learning_service or LearningService()
        self._pool = ThreadPoolExecutor(max_workers=self.config.shadow_max_parallel_workers)

    def run(self, symbol: str, label_name: LabelName = LabelName.DIRECTION) -> None:
        """Synchronously evaluates every SHADOW model for `label_name`
        against `symbol`, recording each as a Continuous Learning
        shadow sample. Never raises - every per-model failure is caught,
        logged, and skipped."""
        shadow_entries = [
            entry for entry in self.registry_service.list_by_state(PromotionState.SHADOW, limit=500)
            if entry.label_name == label_name
        ]
        if not shadow_entries:
            return

        futures = [self._pool.submit(self._evaluate_one, entry.model_id, symbol) for entry in shadow_entries]
        for future in futures:
            future.result()  # each _evaluate_one already swallows its own errors

    def submit(self, symbol: str, label_name: LabelName = LabelName.DIRECTION) -> None:
        """Fire-and-forget: schedules `run` on a background thread and
        returns immediately, never blocking the caller (a live
        prediction) on shadow-model evaluation."""
        self._pool.submit(self._run_swallowing_errors, symbol, label_name)

    def _run_swallowing_errors(self, symbol: str, label_name: LabelName) -> None:
        try:
            self.run(symbol, label_name)
        except Exception as exc:
            log_event(
                logger, component="model_serving", module="model_serving.shadow", operation="submit",
                status=STATUS_ERROR, symbol=symbol, error_type=type(exc).__name__, level=logging.WARNING,
            )

    def _evaluate_one(self, model_id: str, symbol: str) -> None:
        try:
            loaded_model = self.loader.load_version_override(model_id)
            adapter = self.inference_engine.adapter_for(loaded_model)
            self.learning_service.record_shadow_vote(adapter, symbol)
        except Exception as exc:
            log_event(
                logger, component="model_serving", module="model_serving.shadow", operation="evaluate_one",
                status=STATUS_ERROR, model_id=model_id, symbol=symbol, error_type=type(exc).__name__,
                level=logging.WARNING,
            )
            return
        log_event(
            logger, component="model_serving", module="model_serving.shadow", operation="evaluate_one",
            status=STATUS_SUCCESS, model_id=model_id, symbol=symbol,
        )

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)
