"""
OptiTrade ML Training Platform — evaluation metrics.

Reuses, rather than duplicates:

  - `sklearn.metrics` for precision/recall/F1/ROC AUC/MAE/RMSE - the
    exact same library `learning/accuracy.py` already uses for
    precision/recall.
  - `learning.calibration.expected_calibration_error` for calibration
    error, called with lightweight duck-typed points (it only ever
    accesses `.evaluated`/`.correct`/`.confidence` - never
    `isinstance`-checked against `EngineOutcomeRecord`), so the exact
    same ECE algorithm scores a raw train/test split here as scores a
    live decision's outcome in Continuous Learning.
  - `research_lab.model_analysis.metrics.{expected_value,sharpe_ratio,
    sortino_ratio,max_drawdown}` directly for the trading-performance
    metrics, including its `_NO_DOWNSIDE_CAP` convention for
    profit_factor's own "no losses at all" edge case.

`profit_factor` (gross gains / gross losses) is the only genuinely new
metric here - nothing else in this codebase computes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
)

from learning.calibration import expected_calibration_error
from research_lab.model_analysis import metrics as trading_metrics
from research_lab.model_analysis.metrics import _NO_DOWNSIDE_CAP


@dataclass
class CalibrationPoint:
    """Minimal duck-typed stand-in for `learning.models.
    EngineOutcomeRecord` - `expected_calibration_error` only ever reads
    these three attributes, never constructs or isinstance-checks the
    type, so a full `EngineOutcomeRecord` (with many fields irrelevant
    to a raw model evaluation) isn't needed to reuse it. Public - both
    `evaluation/evaluator.py` and `calibration/calibrator.py` build
    calibration-error input from raw predictions this same way."""

    evaluated: bool
    correct: bool
    confidence: float


def calibration_error_from_predictions(y_true: np.ndarray, y_proba: np.ndarray, num_bins: int = 10) -> float:
    """Builds `CalibrationPoint`s from raw predicted-probability
    matrices (argmax = predicted class, its own probability = reported
    confidence) and scores them with the exact same ECE algorithm
    Continuous Learning uses for a live engine's outcomes."""
    predicted_class = np.argmax(y_proba, axis=1)
    confidences = np.max(y_proba, axis=1)
    correct = np.asarray(y_true) == predicted_class
    points = [
        CalibrationPoint(evaluated=True, correct=bool(c), confidence=float(conf))
        for c, conf in zip(correct, confidences)
    ]
    return expected_calibration_error(points, num_bins)


def classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, y_proba: Optional[np.ndarray] = None, calibration_bins: int = 10,
) -> dict:
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
    }

    if y_proba is not None:
        metrics["calibration_error"] = calibration_error_from_predictions(y_true, y_proba, calibration_bins)

        unique_classes = np.unique(y_true)
        if len(unique_classes) == 2:
            metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba[:, 1]))
        elif len(unique_classes) > 2:
            metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba, multi_class="ovr", average="macro"))

    return metrics


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mse = mean_squared_error(y_true, y_pred)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mse)),
    }


def profit_factor(returns: List[float]) -> float:
    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value < 0))
    if losses == 0:
        return _NO_DOWNSIDE_CAP if gains > 0 else 0.0
    return gains / losses


def trading_performance_metrics(returns: List[float], risk_free_rate: float = 0.0) -> dict:
    return {
        "expected_value": trading_metrics.expected_value(returns),
        "sharpe_ratio": trading_metrics.sharpe_ratio(returns, risk_free_rate),
        "sortino_ratio": trading_metrics.sortino_ratio(returns, risk_free_rate),
        "max_drawdown": trading_metrics.max_drawdown(returns),
        "profit_factor": profit_factor(returns),
    }
