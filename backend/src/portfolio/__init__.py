"""
OptiTrade Portfolio Intelligence Platform.

Production, stateful portfolio management sitting alongside `pipeline`/
`model_serving` on the live side of the architecture: multiple
portfolios, cash, positions (derived from a `Transaction` ledger),
realized/unrealized P&L, dividends, fees, taxes, and history
(`service.py`); position analytics (`analytics.py`); risk analytics
(`risk.py`); optimization (`optimization.py`, optionally tilted by
`pipeline.service.PipelineService`'s own forward views); rebalancing
(`rebalancing.py`); scenario analysis (`scenarios.py`); a
recommendation engine combining Decision Engine signals with portfolio
analytics (`recommendations.py`); and a dashboard composing all of the
above with zero duplicated calculation (`dashboard.py`).

Like `model_serving`, this package executes during live production
requests and must never depend on `research_lab` - see
`tests/test_research_isolation.py`.
"""
from portfolio.analytics import PositionAnalyticsService
from portfolio.dashboard import PortfolioDashboardService
from portfolio.optimization import PortfolioOptimizationService
from portfolio.rebalancing import RebalancingService
from portfolio.recommendations import RecommendationEngine
from portfolio.risk import RiskAnalyticsService
from portfolio.scenarios import ScenarioAnalysisService
from portfolio.service import PortfolioService

__all__ = [
    "PortfolioService",
    "PositionAnalyticsService",
    "RiskAnalyticsService",
    "PortfolioOptimizationService",
    "RebalancingService",
    "ScenarioAnalysisService",
    "RecommendationEngine",
    "PortfolioDashboardService",
]
