"""
OptiTrade Research Lab — Hypothesis Registry.

Every experiment must begin with a written hypothesis. Hypotheses are
never deleted - accepted, rejected, and inconclusive outcomes are all
kept permanently, so a failed experiment's reasoning is never lost.
"""
from research_lab.hypothesis.service import HypothesisRegistry

__all__ = ["HypothesisRegistry"]
