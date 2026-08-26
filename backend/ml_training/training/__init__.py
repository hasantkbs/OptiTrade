"""
OptiTrade ML Training Platform — Training Pipeline.

Production trainers for LightGBM, XGBoost, CatBoost, and Random
Forest, every one exposing the exact same interface
(`ModelTrainerProtocol`): fit, predict, predict_proba, feature
importance, save/load.
"""
from ml_training.training.service import create_trainer
from ml_training.training.interfaces import ModelTrainerProtocol

__all__ = ["create_trainer", "ModelTrainerProtocol"]
