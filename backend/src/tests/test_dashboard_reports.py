"""Tests for dashboard/reports.py. Real PostgreSQL throughout."""
from datetime import datetime, timezone

import pytest

from dashboard.models import ReportPeriod
from dashboard.overview import OverviewDashboardService
from dashboard.repository import DashboardRepository
from dashboard.reports import ReportService
from learning.persistence import LearningRepository


@pytest.fixture
def repo():
    repository = DashboardRepository()
    yield repository
    repository.close()


@pytest.fixture
def service(repo):
    return ReportService(repo, overview_service=OverviewDashboardService(repo, learning_repository=LearningRepository()))


def test_generate_daily_report(service):
    report = service.generate(ReportPeriod.DAILY)
    assert report.period == ReportPeriod.DAILY
    assert report.period_start < report.period_end
    assert "total_users" in report.summary


def test_generate_weekly_report(service):
    report = service.generate(ReportPeriod.WEEKLY)
    assert report.period == ReportPeriod.WEEKLY
    assert (report.period_end - report.period_start).days == 7


def test_generate_monthly_report(service):
    reference = datetime(2026, 7, 15, tzinfo=timezone.utc)
    report = service.generate(ReportPeriod.MONTHLY, reference=reference)
    assert report.period_start == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert report.period_end == datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_generate_yearly_report(service):
    reference = datetime(2026, 7, 15, tzinfo=timezone.utc)
    report = service.generate(ReportPeriod.YEARLY, reference=reference)
    assert report.period_start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert report.period_end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_december_monthly_report_rolls_into_next_year(service):
    reference = datetime(2026, 12, 15, tzinfo=timezone.utc)
    report = service.generate(ReportPeriod.MONTHLY, reference=reference)
    assert report.period_start == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert report.period_end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_to_json(service):
    report = service.generate(ReportPeriod.DAILY)
    json_str = service.to_json(report)
    assert '"period"' in json_str
    assert '"total_users"' in json_str


def test_to_csv(service):
    report = service.generate(ReportPeriod.DAILY)
    csv_str = service.to_csv(report)
    lines = csv_str.strip().splitlines()
    assert lines[0] == "metric,value"
    assert any(line.startswith("total_users,") for line in lines)


def test_unknown_period_raises():
    from dashboard.reports import _period_bounds
    with pytest.raises(ValueError):
        _period_bounds("not-a-period", datetime.now(timezone.utc))
