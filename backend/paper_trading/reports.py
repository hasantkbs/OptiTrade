"""OptiTrade Paper Trading & Trade Journal Platform — daily/weekly/monthly/yearly reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from core.report_periods import period_bounds as _period_bounds
from paper_trading.analytics import AnalyticsService, compute_profit_factor
from paper_trading.models import ClosedTrade, PaperAccount, ReportPeriod, TradeReport


class ReportService:
    def __init__(self, analytics_service: AnalyticsService) -> None:
        self._analytics_service = analytics_service

    def generate(
        self, account: PaperAccount, period: ReportPeriod, reference: Optional[datetime] = None,
    ) -> TradeReport:
        reference = reference or datetime.now(timezone.utc)
        start, end = _period_bounds(period, reference)

        closed_trades = self._analytics_service.get_closed_trades(account)
        in_period = [trade for trade in closed_trades if start <= trade.exit_time < end]
        wins = [trade for trade in in_period if trade.net_pnl > 0]

        return TradeReport(
            account_id=account.id, period=period, period_start=start, period_end=end,
            total_trades=len(in_period), net_pnl=sum(trade.net_pnl for trade in in_period),
            win_rate=(len(wins) / len(in_period)) if in_period else 0.0,
            profit_factor=compute_profit_factor(in_period) if in_period else None,
            best_trade=self._best(in_period), worst_trade=self._worst(in_period),
        )

    @staticmethod
    def _best(trades) -> Optional[ClosedTrade]:
        return max(trades, key=lambda trade: trade.net_pnl) if trades else None

    @staticmethod
    def _worst(trades) -> Optional[ClosedTrade]:
        return min(trades, key=lambda trade: trade.net_pnl) if trades else None
