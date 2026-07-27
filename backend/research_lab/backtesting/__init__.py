"""
OptiTrade Research Lab — Backtesting.

Five methods (walk-forward, rolling window, purged CV, stress testing,
out-of-sample) all operating on a chronological historical return
series sourced from Continuous Learning's already-evaluated engine
outcomes - never re-executing any engine, never touching production
inference.
"""
from research_lab.backtesting.engine import BacktestEngine
from research_lab.backtesting.service import BacktestService

__all__ = ["BacktestEngine", "BacktestService"]
