"""
OptiTrade Watchlist & Alert Platform.

Unlimited watchlists with favorites/folders/tags/notes
(`watchlist_service.py`); price, technical, Decision Engine, news, and
portfolio alerts (`price_alerts.py`/`technical_alerts.py`/
`alert_engine.py`/`news_alerts.py`/`portfolio_alerts.py`); notification
payload preparation only, no provider implementation yet
(`notification_router.py`); and an incremental, parallel, retrying,
deduplicating, cooldown-aware scheduler (`scheduler.py`).

Integrates directly with the existing production architecture -
Feature Store (technical indicator values), Decision Engine/Pipeline
(BUY/SELL/confidence/expected-return/risk signals), Continuous
Learning (engine accuracy context), and `portfolio` (allocation/VaR/
drawdown/concentration) - never `research_lab`, guarded the same way
every other production package already is (see
`tests/test_research_isolation.py`).
"""
from watchlist.alert_engine import AlertEngine
from watchlist.news_alerts import NewsAlertEvaluator
from watchlist.notification_router import InMemoryNotificationProvider, NotificationRouter
from watchlist.portfolio_alerts import PortfolioAlertEvaluator
from watchlist.price_alerts import PriceAlertEvaluator
from watchlist.scheduler import AlertScheduler
from watchlist.technical_alerts import TechnicalAlertEvaluator
from watchlist.watchlist_service import WatchlistService

__all__ = [
    "WatchlistService",
    "AlertEngine",
    "PriceAlertEvaluator",
    "TechnicalAlertEvaluator",
    "PortfolioAlertEvaluator",
    "NewsAlertEvaluator",
    "NotificationRouter",
    "InMemoryNotificationProvider",
    "AlertScheduler",
]
