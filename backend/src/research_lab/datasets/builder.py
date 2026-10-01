"""
OptiTrade Research Lab — dataset builder.

Rebuilds a `DatasetDefinition` into an actual `pandas.DataFrame` on
demand, reading every (symbol, feature_name) history exclusively
through `feature_store.service.FeatureStoreService.get_feature_history`
- the Feature Store is the only data source; nothing is cached or
duplicated here.
"""
from __future__ import annotations

import pandas as pd

from feature_store.service import FeatureStoreService
from research_lab.models import DatasetDefinition


def build(definition: DatasetDefinition, feature_store: FeatureStoreService) -> pd.DataFrame:
    """Returns a long-format DataFrame with columns
    `[symbol, feature_name, value, event_timestamp]` - one row per
    recorded feature value in the definition's date range."""
    rows = []
    for symbol in definition.symbols:
        for feature_name in definition.feature_names:
            history = feature_store.get_feature_history(symbol, feature_name, definition.start, definition.end)
            for record in history:
                rows.append(
                    {
                        "symbol": symbol, "feature_name": feature_name,
                        "value": record.value, "event_timestamp": record.event_timestamp,
                    }
                )
    return pd.DataFrame(rows, columns=["symbol", "feature_name", "value", "event_timestamp"])
