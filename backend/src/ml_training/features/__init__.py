"""
OptiTrade ML Training Platform — Feature Extraction.

Automatically loads feature vectors from the Feature Store, grouped
into technical/fundamental/news/risk/regime/relative_strength
categories. Never computes a feature itself - purely reads.
"""
from ml_training.features.extractor import FeatureExtractor

__all__ = ["FeatureExtractor"]
