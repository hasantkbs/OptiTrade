"""
OptiTrade Analytics & Dashboard Platform — daily/weekly/monthly/yearly
reports, with JSON and CSV export.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from dashboard.models import DashboardReport, ReportPeriod
from dashboard.overview import OverviewDashboardService
from dashboard.repository import DashboardRepository


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
    def __init__(self, repository: DashboardRepository, overview_service: Optional[OverviewDashboardService] = None) -> None:
        self._repository = repository
        self._overview_service = overview_service or OverviewDashboardService(repository)

    def generate(self, period: ReportPeriod, reference: Optional[datetime] = None) -> DashboardReport:
        reference = reference or datetime.now(timezone.utc)
        start, end = _period_bounds(period, reference)

        overview = self._overview_service.build()
        triggers_in_period = [
            row for row in self._repository.list_alert_triggers(since=start, limit=10_000) if row["triggered_at"] < end
        ]
        executions_in_period = [
            row for row in self._repository.list_recent_decision_executions(limit=10_000)
            if start <= row["timestamp"] < end
        ]

        summary = {
            "total_users": overview.total_users,
            "active_users": overview.active_users,
            "total_portfolios": overview.total_portfolios,
            "total_watchlists": overview.total_watchlists,
            "total_alerts": overview.total_alerts,
            "total_paper_accounts": overview.total_paper_accounts,
            "total_models": overview.total_models,
            "active_engines": overview.active_engines,
            "learning_samples_tracked": overview.learning_status.total_samples,
            "learning_samples_pending": overview.learning_status.pending_samples,
            "alerts_fired_in_period": len(triggers_in_period),
            "decisions_made_in_period": len(executions_in_period),
        }
        return DashboardReport(period=period, period_start=start, period_end=end, summary=summary)

    @staticmethod
    def to_json(report: DashboardReport) -> str:
        return report.model_dump_json(indent=2)

    @staticmethod
    def to_csv(report: DashboardReport) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["metric", "value"])
        writer.writerow(["period", report.period.value])
        writer.writerow(["period_start", report.period_start.isoformat()])
        writer.writerow(["period_end", report.period_end.isoformat()])
        for key, value in report.summary.items():
            writer.writerow([key, value])
        return buffer.getvalue()
