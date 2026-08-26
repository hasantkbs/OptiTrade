"""
OptiTrade ML Training Platform — Label Generation.

Ground-truth direction, expected return, expected volatility, trend
continuation/reversal, breakout, and rejection labels, all derived
purely from realized forward price action.
"""
from ml_training.labels.generator import generate_labels

__all__ = ["generate_labels"]
