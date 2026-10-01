"""
OptiTrade Research Lab — Feature Analysis.

Tracks feature importance (persisted from engines' already-computed
values), correlation, stability, and drift - all reading historical
features exclusively through the Feature Store.
"""
from research_lab.feature_analysis.service import FeatureAnalysisService

__all__ = ["FeatureAnalysisService"]
