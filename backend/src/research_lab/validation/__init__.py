"""
OptiTrade Research Lab — Decision Engine quantitative validation.

Reconstructs the live Decision Engine's actual historical track record
from already-realized Continuous Learning outcomes (never re-executing
any engine, never fetching a hypothetical historical feature vector),
cost-adjusts it via `paper_trading.execution.ExecutionEngine`'s existing
slippage/spread/commission/tax model, and reports the full statistical
picture: win rate, profit factor, expectancy, Sharpe/Sortino/max
drawdown (via `core.performance_metrics`), equity curve, monthly/yearly
returns, exposure, and a real buy-and-hold benchmark comparison.
"""
from research_lab.validation.service import ValidationService

__all__ = ["ValidationService"]
