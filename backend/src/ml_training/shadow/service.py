"""
OptiTrade ML Training Platform — shadow deployment service.

Deploys a registered model as a shadow voting engine (registers an
`MLModelVotingEngineAdapter` into `engine_registry.default_registry`),
runs shadow passes by delegating straight to
`research_lab.shadow.service.ShadowEvaluationService.run_shadow_pass`,
and advances Continuous Learning by delegating straight to
`learning.service.LearningService.run_learning_cycle` - the exact same
learning cycle every other voting engine's shadow votes already flow
through, so a model's accuracy/weight/calibration/drift history is
computed identically to Technical/Fundamental/News, with zero new
learning logic. This service NEVER promotes a model - promotion is
`ml_training.registry.service.ModelRegistryService`'s responsibility,
and always requires a human `approved_by`.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from engine_registry.registry import EngineRegistry, default_registry
from learning.models import LearningSample
from learning.scheduler import LearningCycleResult
from learning.service import LearningService
from ml_training.exceptions import InvalidPromotionError
from ml_training.models import ModelAlgorithm, PromotionState, TaskType
from ml_training.registry.service import ModelRegistryService
from ml_training.shadow.adapter import MLModelVotingEngineAdapter
from ml_training.training.service import create_trainer
from research_lab.shadow.service import ShadowEvaluationService

logger = logging.getLogger(__name__)


class MLShadowService:
    def __init__(
        self,
        registry_service: Optional[ModelRegistryService] = None,
        engine_registry: Optional[EngineRegistry] = None,
        shadow_evaluation_service: Optional[ShadowEvaluationService] = None,
        learning_service: Optional[LearningService] = None,
    ) -> None:
        self.registry_service = registry_service or ModelRegistryService()
        # NOT `engine_registry or default_registry`: EngineRegistry
        # defines __len__, so a caller-supplied *empty* registry (the
        # common case in tests, and for a fresh isolated registry) is
        # falsy and would silently fall through to the wrong registry.
        self.engine_registry = engine_registry if engine_registry is not None else default_registry
        self.shadow_evaluation_service = shadow_evaluation_service or ShadowEvaluationService()
        self.learning_service = learning_service or LearningService()

    def deploy_shadow(self, model_id: str) -> MLModelVotingEngineAdapter:
        """Loads the registered model's artifact, wraps it as a voting
        engine, and registers it into `engine_registry` - transitioning
        the registry entry CANDIDATE -> SHADOW in the process. Raises
        if the entry isn't currently CANDIDATE (an already-SHADOW/ACTIVE
        model is already deployed; re-deploying it is a caller bug, not
        something to silently no-op)."""
        entry = self.registry_service.get(model_id)
        if entry is None:
            raise InvalidPromotionError(f"no registered model with model_id {model_id!r}")

        trainer = create_trainer(ModelAlgorithm(entry.algorithm), TaskType.CLASSIFICATION, entry.feature_list)
        trainer.load(entry.artifact_path)

        adapter = MLModelVotingEngineAdapter(
            model_id=entry.model_id, engine_version=entry.engine_version,
            trainer=trainer, feature_names=entry.feature_list,
        )
        self.engine_registry.register(adapter)
        self.registry_service.start_shadow(model_id)

        log_event(
            logger, component="ml_training", module="ml_training.shadow.service", operation="deploy_shadow",
            status=STATUS_SUCCESS, model_id=model_id, engine_name=adapter.engine_name,
        )
        return adapter

    def run_shadow_pass(self, model_id: str, symbols: List[str]) -> List[LearningSample]:
        entry = self.registry_service.get(model_id)
        if entry is None:
            raise InvalidPromotionError(f"no registered model with model_id {model_id!r}")
        if entry.promotion_state != PromotionState.SHADOW:
            raise InvalidPromotionError(
                f"model {model_id!r} must be deployed to SHADOW before running a shadow pass "
                f"(currently {entry.promotion_state.value!r})"
            )

        adapter = self.engine_registry.get(entry.engine_name, entry.engine_version)
        return self.shadow_evaluation_service.run_shadow_pass(adapter, symbols)

    def run_learning_cycle(self, now=None) -> LearningCycleResult:
        """Evaluates pending shadow (and live) samples and recomputes
        accuracy/weight/drift for every observed engine - including
        every deployed shadow model. Never promotes anything itself."""
        return self.learning_service.run_learning_cycle(now)
