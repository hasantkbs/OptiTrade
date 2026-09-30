"""
OptiTrade Research Lab — feature stability analysis.

A feature that swings wildly over time is less trustworthy as a signal
input than one that changes gradually. Stability is derived from the
coefficient of variation (`stdev / |mean|`) of the feature's historical
values over the window - a low CV (stable) maps to a high stability
score.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np

from feature_store.service import FeatureStoreService
from research_lab.models import FeatureStabilityRecord


def compute_stability(
    feature_store: FeatureStoreService,
    symbol: str,
    feature_name: str,
    start: datetime,
    end: datetime,
) -> Optional[FeatureStabilityRecord]:
    history = feature_store.get_feature_history(symbol, feature_name, start, end)
    if len(history) < 2:
        return None

    values = np.array([record.value for record in history])
    mean = float(np.mean(values))
    std = float(np.std(values))

    coefficient_of_variation = abs(std / mean) if mean != 0 else (0.0 if std == 0 else float("inf"))
    stability_score = max(0.0, min(1.0, 1.0 - coefficient_of_variation))

    return FeatureStabilityRecord(
        symbol=symbol, feature_name=feature_name, stability_score=stability_score,
        coefficient_of_variation=coefficient_of_variation if coefficient_of_variation != float("inf") else 999.0,
        sample_count=len(history), window_start=start, window_end=end,
        computed_at=datetime.now(timezone.utc),
    )
