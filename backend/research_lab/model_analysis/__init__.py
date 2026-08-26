"""
OptiTrade Research Lab — Model Analysis.

Combines Continuous Learning's accuracy/precision/recall/calibration
with Sharpe, Sortino, max drawdown, and expected value - all computed
from the same evaluated engine outcome history, never re-tracked.
"""
from research_lab.model_analysis.service import ModelAnalysisService

__all__ = ["ModelAnalysisService"]
