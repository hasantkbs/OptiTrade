"""
OptiTrade ML Training Platform — Optuna hyperparameter optimization.

Bayesian optimization via Optuna's default TPE sampler. Early stopping
happens at the level each trial actually trains at: every trial fits a
real trainer with `X_val`/`y_val`, so the SAME per-algorithm early-
stopping mechanism `training/*_trainer.py` already implements (LightGBM/
XGBoost/CatBoost's `early_stopping_rounds`) is active on every single
trial - optimization never has to re-implement it. Parallel trials are
Optuna's own `n_jobs` support. Best-model persistence keeps the actual
fitted trainer with the best score (not just its hyperparameters, which
would require an extra re-fit) via a thread-safe holder, since parallel
trials (`n_jobs > 1`) run the objective function concurrently.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, List, Optional, Tuple

import optuna
from sklearn.metrics import accuracy_score, mean_squared_error

from core.structured_logging import STATUS_SUCCESS, log_event
from ml_training.config import MLTrainingConfig
from ml_training.models import ModelAlgorithm, OptimizationResult, TaskType
from ml_training.optimization.search_spaces import get_search_space
from ml_training.training.base import BaseTrainer
from ml_training.training.service import create_trainer

logger = logging.getLogger(__name__)

optuna.logging.set_verbosity(optuna.logging.WARNING)

ScoringFunction = Callable[[BaseTrainer, "np.ndarray", "np.ndarray"], float]


def default_classification_score(trainer: BaseTrainer, X_val, y_val) -> float:
    return float(accuracy_score(y_val, trainer.predict(X_val)))


def default_regression_score(trainer: BaseTrainer, X_val, y_val) -> float:
    # Negated so "maximize" is always the right optimization direction
    # regardless of task type.
    return -float(mean_squared_error(y_val, trainer.predict(X_val)))


def _default_scoring_function(task_type: TaskType) -> ScoringFunction:
    return default_classification_score if task_type == TaskType.CLASSIFICATION else default_regression_score


class HyperparameterOptimizer:
    def __init__(self, config: Optional[MLTrainingConfig] = None) -> None:
        self.config = config or MLTrainingConfig.from_env()

    def optimize(
        self,
        model_id: str,
        algorithm: ModelAlgorithm,
        task_type: TaskType,
        feature_names: List[str],
        X_train, y_train, X_val, y_val,
        scoring_function: Optional[ScoringFunction] = None,
        n_trials: Optional[int] = None,
        n_jobs: Optional[int] = None,
    ) -> Tuple[OptimizationResult, BaseTrainer]:
        scoring_function = scoring_function or _default_scoring_function(task_type)
        search_space = get_search_space(algorithm)

        best_lock = threading.Lock()
        best_holder: Dict[str, object] = {"trainer": None, "score": None}

        def objective(trial: optuna.Trial) -> float:
            params = search_space(trial)
            trainer = create_trainer(algorithm, task_type, feature_names, hyperparameters=params, config=self.config)
            trainer.fit(X_train, y_train, X_val, y_val)
            score = scoring_function(trainer, X_val, y_val)

            with best_lock:
                if best_holder["score"] is None or score > best_holder["score"]:
                    best_holder["score"] = score
                    best_holder["trainer"] = trainer
            return score

        sampler = optuna.samplers.TPESampler(seed=self.config.random_state)
        study = optuna.create_study(direction="maximize", sampler=sampler, study_name=f"{model_id}-{algorithm.value}")
        study.optimize(
            objective,
            n_trials=n_trials or self.config.optuna_n_trials,
            n_jobs=n_jobs or self.config.optuna_n_jobs,
            timeout=self.config.optuna_timeout_seconds or None,
        )

        result = OptimizationResult(
            model_id=model_id, algorithm=algorithm,
            best_params={key: float(value) for key, value in study.best_params.items()},
            best_score=study.best_value, n_trials=len(study.trials), study_name=study.study_name,
        )

        log_event(
            logger, component="ml_training", module="ml_training.optimization.optimizer", operation="optimize",
            status=STATUS_SUCCESS, model_id=model_id, algorithm=algorithm.value,
            best_score=result.best_score, n_trials=result.n_trials,
        )
        return result, best_holder["trainer"]

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
        result, best_trainer = self.optimize(
            model_id, algorithm, task_type, feature_names, X_train, y_train, X_val, y_val,
            scoring_function, n_trials, n_jobs,
        )
        best_trainer.save(artifact_path)
        return result, best_trainer
