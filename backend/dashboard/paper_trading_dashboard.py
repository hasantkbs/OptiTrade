"""
OptiTrade Analytics & Dashboard Platform — Paper Trading dashboard.

Reuses `paper_trading.analytics.AnalyticsService` directly for win
rate/expectancy/equity-curve/monthly-performance (no re-derivation of
FIFO trade matching); journal statistics are the one genuinely new
aggregation this module adds, straight from `paper_trading`'s own
journal entries.
"""
from __future__ import annotations

import logging
import statistics
import time
from collections import Counter
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from dashboard.models import JournalStatistics, PaperTradingDashboardView, TimeSeriesPoint
from paper_trading.analytics import AnalyticsService
from paper_trading.exceptions import AccountNotFoundError
from paper_trading.models import TradeJournalEntry
from paper_trading.repository import PaperTradingRepository

logger = logging.getLogger(__name__)
_MODULE = "dashboard.paper_trading_dashboard"
_COMPONENT = "dashboard"


class PaperTradingDashboardService:
    def __init__(
        self,
        paper_trading_repository: Optional[PaperTradingRepository] = None,
        analytics_service: Optional[AnalyticsService] = None,
    ) -> None:
        self._repository = paper_trading_repository or PaperTradingRepository()
        self._analytics_service = analytics_service or AnalyticsService(self._repository)

    def build(self, account_id: int) -> PaperTradingDashboardView:
        started_at = time.perf_counter()
        account = self._repository.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(f"paper trading account {account_id} not found")

        summary = self._analytics_service.get_summary(account)
        equity_curve = self._analytics_service.get_equity_curve(account)
        monthly_performance = self._analytics_service.get_monthly_performance(account)
        journal_entries = self._repository.list_journal_entries(account_id)

        view = PaperTradingDashboardView(
            account_id=account_id, win_rate=summary.win_rate, expectancy=summary.expectancy,
            equity_curve=[TimeSeriesPoint(timestamp=point.as_of, value=point.equity) for point in equity_curve],
            monthly_performance=[entry.model_dump() for entry in monthly_performance],
            journal_statistics=self._journal_statistics(journal_entries),
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, account_id=account_id,
        )
        return view

    @staticmethod
    def _journal_statistics(entries: List[TradeJournalEntry]) -> JournalStatistics:
        confidences = [entry.confidence for entry in entries if entry.confidence is not None]
        tag_counts = Counter(tag for entry in entries for tag in entry.tags)
        return JournalStatistics(
            total_entries=len(entries),
            entries_by_decision=dict(Counter(entry.decision.value for entry in entries if entry.decision is not None)),
            entries_by_regime=dict(Counter(entry.market_regime.value for entry in entries)),
            average_confidence=statistics.mean(confidences) if confidences else None,
            most_common_tags=[tag for tag, _ in tag_counts.most_common(10)],
        )
