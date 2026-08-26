"""
OptiTrade Research Lab — feature importance tracking.

Never recomputes importance itself - every voting engine's `analyze()`
already returns a `feature_importance: Dict[str, float]` (see
`engines/technical/engine.py` / `engines/fundamental/engine.py`). This
module only turns that already-computed dict into persisted,
time-stamped `FeatureImportanceRecord`s for later trend analysis.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from research_lab.models import FeatureImportanceRecord


def to_records(
    symbol: str, engine_name: str, feature_importance: Dict[str, float], computed_at: Optional[datetime] = None,
) -> List[FeatureImportanceRecord]:
    computed_at = computed_at or datetime.now(timezone.utc)
    return [
        FeatureImportanceRecord(
            symbol=symbol, engine_name=engine_name, feature_name=feature_name,
            importance=importance, computed_at=computed_at,
        )
        for feature_name, importance in feature_importance.items()
    ]
