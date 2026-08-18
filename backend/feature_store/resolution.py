"""
OptiTrade Feature Store — staleness-aware feature resolution.

The shared "check the Feature Store first (per feature name); anything
missing or older than a staleness cutoff is recomputed and written
back" orchestration - previously duplicated verbatim between
`engines/technical/feature_adapter.py` and
`engines/fundamental/feature_adapter.py`, and available to any future
engine with the same shape: a fixed feature-name list, a per-symbol
`compute_all(symbol) -> Dict[str, float]` callback, and a
`max_feature_age_seconds` staleness cutoff.

This is Feature-Store-backed (Redis-cached, Postgres-persisted, shared
across processes via `FeatureStoreService`), not an in-memory
`core.cache_manager.TTLCache` - the two engines' staleness check reads
each feature's own `event_timestamp` rather than a fixed
insertion-time TTL, which is what already correctly models "technical
indicators go stale in minutes, fundamentals in a day" with two very
different `max_feature_age_seconds` per engine. Preserving that
existing semantic (not forcing a different cache abstraction onto it)
is the point of this extraction - only the duplicated control flow
moves, not the underlying mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List

from feature_store.service import FeatureStoreService


@dataclass
class FeatureResolution:
    """The resolved features plus which were served from cache vs.
    computed fresh this call."""

    values: Dict[str, float] = field(default_factory=dict)
    from_cache: List[str] = field(default_factory=list)
    computed_fresh: List[str] = field(default_factory=list)


def resolve_features(
    feature_store: FeatureStoreService,
    symbol: str,
    feature_names: List[str],
    max_age_seconds: float,
    compute_all: Callable[[str], Dict[str, float]],
) -> FeatureResolution:
    """For each of `feature_names`, serves the Feature Store's value if
    it exists and isn't older than `max_age_seconds`; anything missing
    or stale is resolved in one `compute_all(symbol)` call (the
    caller's own reused computation logic - this function has no
    opinion on how features are actually computed)."""
    resolution = FeatureResolution()
    missing: List[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)

    for name in feature_names:
        record = feature_store.get_latest_feature(symbol, name)
        if record is not None and record.event_timestamp >= cutoff:
            resolution.values[name] = record.value
            resolution.from_cache.append(name)
        else:
            missing.append(name)

    if missing:
        fresh = compute_all(symbol)
        for name in missing:
            if name in fresh:
                resolution.values[name] = fresh[name]
                resolution.computed_fresh.append(name)

    return resolution
