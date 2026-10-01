"""
OptiTrade Research Lab — Experiment management.

Lifecycle: draft -> running -> completed -> promoted/rejected -> archived.
Every experiment is created with a written hypothesis and is never
deleted, regardless of outcome.
"""
from research_lab.experiments.service import ExperimentService

__all__ = ["ExperimentService"]
