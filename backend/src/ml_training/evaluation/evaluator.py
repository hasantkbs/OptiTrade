"""
OptiTrade ML Training Platform — model evaluation.

Automatically computes every metric the platform requires from one
fitted trainer: classification or regression metrics (whichever
matches `trainer.task_type`) plus, when a realized-return series is
available (see `datasets`' `LabelSet.expected_return` per test sample),
the trading-performance metrics.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from core.structured_logging import STATUS_SUCCESS, log_event
from ml_training.config import MLTrainingConfig
from ml_training.evaluation import metrics as metrics_module
from ml_training.models import ModelMetrics, TaskType
from ml_training.training.base import BaseTrainer

logger = logging.getLogger(__name__)


class ModelEvaluator:
    def __init__(self, config: Optional[MLTrainingConfig] = None) -> None:
        self.config = config or MLTrainingConfig.from_env()

    def evaluate(
        self,
        trainer: BaseTrainer,
        X_test: np.ndarray,
        y_test: np.ndarray,
        actual_returns: Optional[List[float]] = None,
    ) -> ModelMetrics:
        y_pred = trainer.predict(X_test)

        if trainer.task_type == TaskType.CLASSIFICATION:
            try:
                y_proba = trainer.predict_proba(X_test)
            except Exception:
                y_proba = None
            base_metrics = metrics_module.classification_metrics(
                y_test, y_pred, y_proba, self.config.calibration_bins,
            )
        else:
            base_metrics = metrics_module.regression_metrics(y_test, y_pred)

        trading_metrics: dict = {}
        if actual_returns:
            trading_metrics = metrics_module.trading_performance_metrics(actual_returns, self.config.risk_free_rate)

        result = ModelMetrics(**base_metrics, **trading_metrics)
        log_event(
            logger, component="ml_training", module="ml_training.evaluation.evaluator", operation="evaluate",
            status=STATUS_SUCCESS, algorithm=trainer.algorithm.value, task_type=trainer.task_type.value,
            sample_count=len(y_test),
        )
        return result
