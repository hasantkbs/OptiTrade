"""
OptiTrade ML Training Platform — SHAP feature importance.

All four algorithms are tree-based (see `training/base.py`'s
docstring), so `shap.TreeExplainer` works uniformly across every one of
them - never a per-algorithm SHAP implementation.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import shap


def compute_shap_importance(model, X_background: np.ndarray, feature_names: List[str]) -> Dict[str, float]:
    """Mean absolute SHAP value per feature, normalized to sum to 1.
    Binary classifiers from different libraries return SHAP arrays of
    different shapes (LightGBM/XGBoost/CatBoost: `(n_samples,
    n_features)`; scikit-learn's RandomForestClassifier:
    `(n_samples, n_features, n_classes)`) - both are handled by
    averaging over every axis except the feature axis."""
    explainer = shap.TreeExplainer(model)
    shap_values = np.asarray(explainer.shap_values(X_background))

    if shap_values.ndim == 3:
        importance = np.mean(np.abs(shap_values), axis=(0, 2))
    else:
        importance = np.mean(np.abs(shap_values), axis=0)

    total = float(importance.sum())
    normalized = importance / total if total > 0 else importance
    return dict(zip(feature_names, (float(v) for v in normalized)))
