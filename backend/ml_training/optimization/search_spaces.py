"""
OptiTrade ML Training Platform — Optuna hyperparameter search spaces.

One function per algorithm, each taking an `optuna.Trial` and
returning the hyperparameters dict `training.create_trainer` already
accepts - so a search space is nothing more than "which values could
this trial's hyperparameters dict contain."
"""
from __future__ import annotations

from typing import Callable, Dict

import optuna

from ml_training.models import ModelAlgorithm


def lightgbm_search_space(trial: optuna.Trial) -> Dict:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "num_leaves": trial.suggest_int("num_leaves", 15, 255),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "max_depth": trial.suggest_int("max_depth", 3, 12),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
    }


def xgboost_search_space(trial: optuna.Trial) -> Dict:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "max_depth": trial.suggest_int("max_depth", 3, 12),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "gamma": trial.suggest_float("gamma", 0.0, 5.0),
    }


def catboost_search_space(trial: optuna.Trial) -> Dict:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "depth": trial.suggest_int("depth", 3, 10),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
    }


def random_forest_search_space(trial: optuna.Trial) -> Dict:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "max_depth": trial.suggest_int("max_depth", 3, 20),
        "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
        "max_features": trial.suggest_float("max_features", 0.3, 1.0),
    }


_SEARCH_SPACES: Dict[ModelAlgorithm, Callable[[optuna.Trial], Dict]] = {
    ModelAlgorithm.LIGHTGBM: lightgbm_search_space,
    ModelAlgorithm.XGBOOST: xgboost_search_space,
    ModelAlgorithm.CATBOOST: catboost_search_space,
    ModelAlgorithm.RANDOM_FOREST: random_forest_search_space,
}


def get_search_space(algorithm: ModelAlgorithm) -> Callable[[optuna.Trial], Dict]:
    return _SEARCH_SPACES[algorithm]
