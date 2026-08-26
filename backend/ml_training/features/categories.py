"""
OptiTrade ML Training Platform — feature categorization.

Reuses each engine's own `ALL_FEATURE_NAMES` list (never a second,
hand-maintained copy of "which features are technical/fundamental/
news") to classify a discovered feature name into a category. `risk`,
`regime`, and `relative_strength` have no producing engine yet under
the frozen architecture - their known-name lists stay empty until one
exists; any feature name that doesn't match a known list (including
future risk/regime/relative-strength features, once an engine writes
them following this exact `ALL_FEATURE_NAMES` convention) falls into
`OTHER` rather than being silently dropped.
"""
from __future__ import annotations

from typing import Dict, List

from engines.fundamental.config import ALL_FEATURE_NAMES as _FUNDAMENTAL_FEATURE_NAMES
from engines.news.config import ALL_FEATURE_NAMES as _NEWS_FEATURE_NAMES
from engines.technical.config import ALL_FEATURE_NAMES as _TECHNICAL_FEATURE_NAMES
from ml_training.models import FeatureCategory

KNOWN_CATEGORY_FEATURES: Dict[FeatureCategory, List[str]] = {
    FeatureCategory.TECHNICAL: list(_TECHNICAL_FEATURE_NAMES),
    FeatureCategory.FUNDAMENTAL: list(_FUNDAMENTAL_FEATURE_NAMES),
    FeatureCategory.NEWS: list(_NEWS_FEATURE_NAMES),
    FeatureCategory.RISK: [],
    FeatureCategory.REGIME: [],
    FeatureCategory.RELATIVE_STRENGTH: [],
}


def categorize(feature_names: List[str]) -> Dict[FeatureCategory, List[str]]:
    """Groups `feature_names` by category. Categories with no matching
    feature are omitted entirely rather than included as empty lists."""
    name_to_category: Dict[str, FeatureCategory] = {
        name: category for category, names in KNOWN_CATEGORY_FEATURES.items() for name in names
    }

    grouped: Dict[FeatureCategory, List[str]] = {}
    for name in feature_names:
        category = name_to_category.get(name, FeatureCategory.OTHER)
        grouped.setdefault(category, []).append(name)
    return grouped
