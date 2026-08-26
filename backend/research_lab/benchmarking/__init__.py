"""
OptiTrade Research Lab — Benchmarking.

Compares engine versions, weighting policies, feature sets, and models
using two-sample statistical tests over historical return series.
"""
from research_lab.benchmarking.service import BenchmarkService

__all__ = ["BenchmarkService"]
