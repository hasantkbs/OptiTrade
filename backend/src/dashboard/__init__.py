"""
OptiTrade Analytics & Dashboard Platform.

A read-only aggregation layer over almost every other production
package: system overview (`overview.py`), Decision Engine metrics
(`engine_dashboard.py`), the ML model registry/training/promotion/
benchmark/feature-importance trail (`model_dashboard.py`), Portfolio
(`portfolio_dashboard.py`), Watchlist (`watchlist_dashboard.py`), Paper
Trading (`paper_trading_dashboard.py`), Continuous Learning
(`learning_dashboard.py`), Alerts (`alert_dashboard.py`), and Market
conditions (`market_dashboard.py`) - plus generic analytics primitives
(`analytics.py`, `charts.py`, `metrics.py`), daily/weekly/monthly/yearly
reports with JSON/CSV export (`reports.py`), and a Redis cache-refresh
scheduler (`scheduler.py`).

`repository.py` is the one place this package reads `ml_training`/
`research_lab`-owned Postgres tables directly via raw SQL, precisely
because `tests/test_research_isolation.py` forbids importing either
package from any production directory - see that module's docstring for
the full reasoning. Every other integration in this package is a normal
Python import of an already-permitted production package (`users`,
`portfolio`, `watchlist`, `paper_trading`, `learning`, `decision_engine`,
`feature_store`, `model_serving`, `core`).
"""
from dashboard.alert_dashboard import AlertDashboardService
from dashboard.engine_dashboard import EngineDashboardService
from dashboard.learning_dashboard import LearningDashboardService
from dashboard.market_dashboard import MarketDashboardService
from dashboard.model_dashboard import ModelDashboardService
from dashboard.overview import OverviewDashboardService
from dashboard.paper_trading_dashboard import PaperTradingDashboardService
from dashboard.portfolio_dashboard import DashboardPortfolioService
from dashboard.repository import DashboardRepository
from dashboard.reports import ReportService
from dashboard.scheduler import DashboardScheduler
from dashboard.service import DashboardService
from dashboard.watchlist_dashboard import WatchlistDashboardService

__all__ = [
    "DashboardRepository",
    "DashboardService",
    "OverviewDashboardService",
    "EngineDashboardService",
    "ModelDashboardService",
    "DashboardPortfolioService",
    "WatchlistDashboardService",
    "PaperTradingDashboardService",
    "LearningDashboardService",
    "AlertDashboardService",
    "MarketDashboardService",
    "ReportService",
    "DashboardScheduler",
]
