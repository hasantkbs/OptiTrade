"""OptiTrade Paper Trading & Trade Journal Platform — daily/weekly/monthly/yearly reports."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from paper_trading.analytics import AnalyticsService, compute_profit_factor
from paper_trading.models import ClosedTrade, PaperAccount, ReportPeriod, TradeReport


def _period_bounds(period: ReportPeriod, reference: datetime) -> Tuple[datetime, datetime]:
    reference = reference.astimezone(timezone.utc)
    if period == ReportPeriod.DAILY:
        start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif period == ReportPeriod.WEEKLY:
        start = (reference - timedelta(days=reference.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
    elif period == ReportPeriod.MONTHLY:
        start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    elif period == ReportPeriod.YEARLY:
        start = reference.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
    else:
        raise ValueError(f"unknown report period {period!r}")
    return start, end


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
