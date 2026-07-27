"""
OptiTrade Research Lab — Shadow Evaluation.

Runs candidate engines outside of any live decision, via
`learning.service.LearningService.record_shadow_vote`. Never affects
production.
"""
from research_lab.shadow.service import ShadowEvaluationService

__all__ = ["ShadowEvaluationService"]
