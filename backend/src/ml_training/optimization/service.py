"""OptiTrade ML Training Platform — optimization service."""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from core.structured_logging import STATUS_SUCCESS, log_event
from ml_training.config import MLTrainingConfig
from ml_training.models import ModelAlgorithm, OptimizationResult, TaskType
from ml_training.optimization.optimizer import HyperparameterOptimizer, ScoringFunction
from ml_training.optimization.repository import OptimizationRepository
from ml_training.training.base import BaseTrainer

logger = logging.getLogger(__name__)


class OptimizationService:
    def __init__(
        self,
        optimizer: Optional[HyperparameterOptimizer] = None,
        repository: Optional[OptimizationRepository] = None,
        config: Optional[MLTrainingConfig] = None,
    ) -> None:
        self.config = config or MLTrainingConfig.from_env()
        self.optimizer = optimizer or HyperparameterOptimizer(config=self.config)
        self.repository = repository or OptimizationRepository()

    def optimize_and_save(
        self,
        model_id: str,
        algorithm: ModelAlgorithm,
        task_type: TaskType,
        feature_names: List[str],
        X_train, y_train, X_val, y_val,
        artifact_path: str,
        scoring_function: Optional[ScoringFunction] = None,
        n_trials: Optional[int] = None,
        n_jobs: Optional[int] = None,
    ) -> Tuple[OptimizationResult, BaseTrainer]:
        result, best_trainer = self.optimizer.optimize_and_save(
            model_id, algorithm, task_type, feature_names, X_train, y_train, X_val, y_val,
            artifact_path, scoring_function, n_trials, n_jobs,
        )
        self.repository.save(result)

        log_event(
            logger, component="ml_training", module="ml_training.optimization.service",
            operation="optimize_and_save", status=STATUS_SUCCESS, model_id=model_id,
            algorithm=algorithm.value, best_score=result.best_score,
        )
        return result, best_trainer

    def get_latest(self, model_id: str) -> Optional[OptimizationResult]:
        return self.repository.get_latest(model_id)

    def list_for_model(self, model_id: str, limit: int = 20) -> List[OptimizationResult]:
        return self.repository.list_for_model(model_id, limit)
