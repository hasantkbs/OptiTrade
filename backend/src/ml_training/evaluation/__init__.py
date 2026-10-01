"""
OptiTrade ML Training Platform — Evaluation.

Automatically computes accuracy, precision, recall, F1, ROC AUC,
calibration error, MAE, RMSE, expected value, Sharpe, Sortino, profit
factor, and maximum drawdown - reusing existing evaluation code
(scikit-learn, `learning.calibration`, `research_lab.model_analysis.
metrics`) wherever it already exists.
"""
from ml_training.evaluation.evaluator import ModelEvaluator

__all__ = ["ModelEvaluator"]
