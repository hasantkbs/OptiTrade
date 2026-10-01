"""
OptiTrade Paper Trading & Trade Journal Platform.

Simulated market execution (slippage, spread, commission, tax,
latency, market-hours validation - `execution.py`) driving a full
order lifecycle (market/limit/stop/take-profit, partial/full fill,
cancel/modify - `orders.py`/`fills.py`); every paper account is backed
by a real `portfolio.PortfolioService` ledger, automatically kept in
sync, alongside Watchlist/Alert integration (`portfolio_sync.py`,
`positions.py`); a trade journal capturing the full decision context
from a single `pipeline.PipelineService.run()` call plus a feature
snapshot, notes, tags, and screenshot metadata (`journal.py`);
analytics (win rate, profit factor, Sharpe/Sortino, max drawdown,
expectancy, equity curve, monthly performance - `analytics.py`) and
daily/weekly/monthly/yearly reports (`reports.py`); and a scheduler that
scans resting LIMIT/STOP/TAKE_PROFIT orders for trigger conditions
(`scheduler.py`).

Integrates directly with `portfolio`, `watchlist`, `pipeline`,
`feature_store`, and (via `pipeline.PipelineService.run()`, which
already records into it) Continuous Learning - never `research_lab`,
guarded the same way every other production package already is (see
`tests/test_research_isolation.py`).
"""
from paper_trading.analytics import AnalyticsService
from paper_trading.execution import ExecutionEngine
from paper_trading.fills import FillService
from paper_trading.journal import JournalService
from paper_trading.orders import OrderService
from paper_trading.portfolio_sync import PortfolioSyncService
from paper_trading.positions import PositionService
from paper_trading.repository import PaperTradingRepository
from paper_trading.reports import ReportService
from paper_trading.scheduler import PaperTradingScheduler
from paper_trading.service import PaperTradingService

__all__ = [
    "PaperTradingRepository",
    "PaperTradingService",
    "ExecutionEngine",
    "OrderService",
    "FillService",
    "PortfolioSyncService",
    "PositionService",
    "JournalService",
    "AnalyticsService",
    "ReportService",
    "PaperTradingScheduler",
]
