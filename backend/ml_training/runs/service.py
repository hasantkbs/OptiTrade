"""OptiTrade ML Training Platform — training run tracking service."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from ml_training.models import (
    LabelName,
    ModelAlgorithm,
    ModelMetrics,
    TaskType,
    TrainingRun,
    TrainingRunStatus,
)
from ml_training.runs.repository import TrainingRunRepository

logger = logging.getLogger(__name__)


class TrainingRunService:
    """Tracks one training run's full lifecycle (RUNNING -> COMPLETED
    or FAILED), tied to the Research Lab experiment that framed it -
    see `ml_training.service.MLTrainingService`, the only caller that
    should invoke `start`/`complete`/`fail`."""

    def __init__(self, repository: Optional[TrainingRunRepository] = None) -> None:
        self.repository = repository or TrainingRunRepository()

    def start(
        self,
        model_id: str,
        algorithm: ModelAlgorithm,
        task_type: TaskType,
        label_name: LabelName,
        horizon_days: int,
        dataset_id: Optional[int],
        experiment_id: Optional[int],
    ) -> TrainingRun:
        run = TrainingRun(
            model_id=model_id, algorithm=algorithm, task_type=task_type, label_name=label_name,
            horizon_days=horizon_days, dataset_id=dataset_id, status=TrainingRunStatus.RUNNING,
            experiment_id=experiment_id,
        )
        run.id = self.repository.save(run)
        log_event(
            logger, component="ml_training", module="ml_training.runs.service", operation="start",
            status=STATUS_SUCCESS, run_id=run.id, model_id=model_id,
        )
        return run

    def complete(
        self, run: TrainingRun, hyperparameters: Dict, metrics: ModelMetrics,
        feature_list: List[str], artifact_path: str,
    ) -> TrainingRun:
        run.hyperparameters = hyperparameters
        run.metrics = metrics
        run.feature_list = feature_list
        run.artifact_path = artifact_path
        run.status = TrainingRunStatus.COMPLETED
        self.repository.update(run)
        log_event(
            logger, component="ml_training", module="ml_training.runs.service", operation="complete",
            status=STATUS_SUCCESS, run_id=run.id, model_id=run.model_id,
        )
        return run

    def fail(self, run: TrainingRun) -> TrainingRun:
        run.status = TrainingRunStatus.FAILED
        self.repository.update(run)
        log_event(
            logger, component="ml_training", module="ml_training.runs.service", operation="fail",
            status=STATUS_SUCCESS, run_id=run.id, model_id=run.model_id, level=logging.WARNING,
        )
        return run

    def get(self, run_id: int) -> Optional[TrainingRun]:
        return self.repository.get(run_id)

    def list_for_experiment(self, experiment_id: int, limit: int = 50) -> List[TrainingRun]:
        return self.repository.list_for_experiment(experiment_id, limit)
