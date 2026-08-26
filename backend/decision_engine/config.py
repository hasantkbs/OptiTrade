"""
OptiTrade Decision Engine — configuration.

Reuses `feature_store.config.FeatureStoreConfig` for PostgreSQL
connection details (the execution-history table lives in the same
`optitrade` database as the feature store) rather than duplicating
connection settings in a second config class.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class DecisionEngineConfig:
    """Decision-Engine-specific runtime settings."""

    default_accuracy_weight: float = 1.0
    aggregation_strategy_version: str = "accuracy_weighted_v1"
    accuracy_feature_name: str = "engine_accuracy_score"

    @classmethod
    def from_env(cls) -> "DecisionEngineConfig":
        load_dotenv()
        return cls(
            default_accuracy_weight=float(
                os.getenv("DECISION_ENGINE_DEFAULT_ACCURACY_WEIGHT", "1.0")
            ),
            aggregation_strategy_version=os.getenv(
                "DECISION_ENGINE_AGGREGATION_STRATEGY_VERSION", "accuracy_weighted_v1"
            ),
            accuracy_feature_name=os.getenv(
                "DECISION_ENGINE_ACCURACY_FEATURE_NAME", "engine_accuracy_score"
            ),
        )
