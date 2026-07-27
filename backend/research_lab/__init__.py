"""
OptiTrade Research Lab.

A fully isolated, offline Quant Research environment. Manages
experiments (draft -> running -> completed -> promoted/rejected ->
archived, each requiring a written hypothesis), backtesting (walk-
forward, rolling window, purged CV, stress testing, out-of-sample),
benchmarking (engine versions, feature sets, weighting policies,
models), feature analysis (importance, correlation, stability, drift),
model analysis (accuracy/calibration reused from Continuous Learning
plus Sharpe/Sortino/drawdown/expected value), shadow evaluation, and
promotion recommendations (never automatic).

MUST NEVER participate in production inference - see
`tests/test_research_isolation.py`, which asserts no production module
ever imports this package.
"""
from research_lab.service import ResearchLabService

__all__ = ["ResearchLabService"]
