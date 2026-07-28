"""
OptiTrade ML Training Platform — Dataset Builder.

Builds point-in-time correct, leakage-free datasets directly from the
Feature Store, for multiple prediction horizons and both Trader and
Investor variants. Persists only version metadata - samples are always
rebuilt on demand.
"""
from ml_training.datasets.service import DatasetService

__all__ = ["DatasetService"]
