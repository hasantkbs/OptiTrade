"""OptiTrade ML Training Platform — trainer factory."""
from __future__ import annotations

from typing import Dict, List, Optional, Type

from ml_training.config import MLTrainingConfig
from ml_training.exceptions import UnknownAlgorithmError
from ml_training.models import ModelAlgorithm, TaskType
from ml_training.training.base import BaseTrainer
from ml_training.training.catboost_trainer import CatBoostTrainer
from ml_training.training.lightgbm_trainer import LightGBMTrainer
from ml_training.training.random_forest_trainer import RandomForestTrainer
from ml_training.training.xgboost_trainer import XGBoostTrainer

_TRAINER_CLASSES: Dict[ModelAlgorithm, Type[BaseTrainer]] = {
    ModelAlgorithm.LIGHTGBM: LightGBMTrainer,
    ModelAlgorithm.XGBOOST: XGBoostTrainer,
    ModelAlgorithm.CATBOOST: CatBoostTrainer,
    ModelAlgorithm.RANDOM_FOREST: RandomForestTrainer,
}


def create_trainer(
    algorithm: ModelAlgorithm,
    task_type: TaskType,
    feature_names: List[str],
    hyperparameters: Optional[Dict] = None,
    config: Optional[MLTrainingConfig] = None,
) -> BaseTrainer:
    trainer_class = _TRAINER_CLASSES.get(algorithm)
    if trainer_class is None:
        raise UnknownAlgorithmError(f"no trainer registered for algorithm {algorithm!r}")
    return trainer_class(task_type=task_type, feature_names=feature_names, hyperparameters=hyperparameters, config=config)
