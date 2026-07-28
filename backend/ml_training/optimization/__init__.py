"""
OptiTrade ML Training Platform — Hyperparameter Optimization.

Bayesian optimization (Optuna's TPE sampler) with per-trial early
stopping (each trial's underlying trainer uses the same eval_set-based
early stopping `training/` already implements), parallel trials
(Optuna's `n_jobs`), and best-model persistence.
"""
from ml_training.optimization.service import OptimizationService

__all__ = ["OptimizationService"]
