"""
OptiTrade ML Training Platform — Model Registry.

Tracks every trained model version (algorithm, dataset, hyperparameters,
metrics, feature list, training date) through a validated promotion
lifecycle: CANDIDATE -> SHADOW -> ACTIVE, or -> ARCHIVED at any point.
Promotion to ACTIVE always requires a human `approved_by` - this
platform never promotes a model on its own.
"""
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.registry.service import ModelRegistryService

__all__ = ["ModelRegistryRepository", "ModelRegistryService"]
