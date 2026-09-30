"""
OptiTrade Research Lab — feature correlation analysis.

Reads two features' historical values via
`feature_store.service.FeatureStoreService.get_feature_history` (never
the live/latest read path) and computes their Pearson correlation.
Values are aligned by matching `event_timestamp` exactly (both features
are normally written by the same engine run, so timestamps line up) -
any timestamp present in only one series is dropped rather than
interpolated, to avoid fabricating data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np

from feature_store.service import FeatureStoreService
from research_lab.models import FeatureCorrelationRecord


def compute_correlation(
    feature_store: FeatureStoreService,
    symbol: str,
    feature_a: str,
    feature_b: str,
    start: datetime,
    end: datetime,
) -> Optional[FeatureCorrelationRecord]:
    history_a = feature_store.get_feature_history(symbol, feature_a, start, end)
    history_b = feature_store.get_feature_history(symbol, feature_b, start, end)

    values_by_timestamp_b = {record.event_timestamp: record.value for record in history_b}
    paired = [
        (record.value, values_by_timestamp_b[record.event_timestamp])
        for record in history_a
        if record.event_timestamp in values_by_timestamp_b
    ]

    if len(paired) < 2:
        return None

    series_a = np.array([pair[0] for pair in paired])
    series_b = np.array([pair[1] for pair in paired])

    if np.std(series_a) == 0 or np.std(series_b) == 0:
        correlation = 0.0
    else:
        correlation = float(np.corrcoef(series_a, series_b)[0, 1])
        correlation = max(-1.0, min(1.0, correlation))

    return FeatureCorrelationRecord(
        symbol=symbol, feature_a=feature_a, feature_b=feature_b, correlation=correlation,
        sample_count=len(paired), window_start=start, window_end=end,
        computed_at=datetime.now(timezone.utc),
    )
