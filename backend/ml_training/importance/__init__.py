"""
OptiTrade ML Training Platform — Feature Importance.

SHAP (TreeExplainer, uniform across all four tree-based algorithms) and
permutation importance (scikit-learn). Persisted to both the Feature
Store and Research Lab's feature analysis.
"""
from ml_training.importance.service import FeatureImportanceService

__all__ = ["FeatureImportanceService"]
