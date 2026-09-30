"""
OptiTrade Research Lab — Datasets.

Persists only reproducible dataset *definitions*; the actual feature
values are always rebuilt on demand from the Feature Store.
"""
from research_lab.datasets.service import DatasetService

__all__ = ["DatasetService"]
