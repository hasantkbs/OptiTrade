"""
OptiTrade ML Training Platform — permutation feature importance.

Reuses `sklearn.inspection.permutation_importance` directly - never
hand-rolls shuffle-and-rescore importance.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
from sklearn.inspection import permutation_importance

from ml_training.training.base import BaseTrainer


def compute_permutation_importance(
    trainer: BaseTrainer, X: np.ndarray, y: np.ndarray, n_repeats: int = 10, random_state: int = 42,
) -> Dict[str, float]:
    """Mean permutation importance per feature, normalized to sum to 1.
    Negative raw scores (a shuffled feature scoring no worse than the
    original by chance - a real, expected outcome for an uninformative
    feature) are clamped to 0 before normalizing, since a negative
    share of "how important is this feature" isn't meaningful in a
    normalized report."""
    result = permutation_importance(
        trainer._model, X, y, n_repeats=n_repeats, random_state=random_state,
    )
    raw = np.clip(result.importances_mean, a_min=0.0, a_max=None)
    total = float(raw.sum())
    normalized = raw / total if total > 0 else raw
    return dict(zip(trainer.feature_names, (float(v) for v in normalized)))
