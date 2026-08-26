"""
OptiTrade Feature Store.

Public entry point for every future engine that needs versioned,
point-in-time-correct feature data: `FeatureStoreService`. Engines should
depend on `feature_store.interfaces` (Protocols) and
`feature_store.models`, not on the concrete Redis/PostgreSQL
implementations directly.
"""
from feature_store.models import FeatureDefinition, FeatureRecord, FeatureValue, ValidationResult
from feature_store.service import FeatureStoreService

__all__ = [
    "FeatureStoreService",
    "FeatureValue",
    "FeatureRecord",
    "FeatureDefinition",
    "ValidationResult",
]
