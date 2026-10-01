"""
Tests for core/report_periods.py - the shared implementation extracted
from dashboard/reports.py and paper_trading/reports.py's previously
duplicated `_period_bounds` (production audit MEDIUM #2). Pure date
math, no infra.
"""
from datetime import datetime, timezone

import pytest

from core.report_periods import period_bounds
from dashboard.models import ReportPeriod as DashboardReportPeriod
from paper_trading.models import ReportPeriod as PaperTradingReportPeriod


def test_daily_bounds_are_midnight_aligned():
    reference = datetime(2026, 7, 15, 14, 30, tzinfo=timezone.utc)
    start, end = period_bounds(DashboardReportPeriod.DAILY, reference)
    assert start == datetime(2026, 7, 15, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 16, tzinfo=timezone.utc)


def test_weekly_bounds_start_on_monday():
    # 2026-07-15 is a Wednesday
    reference = datetime(2026, 7, 15, 14, 30, tzinfo=timezone.utc)
    start, end = period_bounds(DashboardReportPeriod.WEEKLY, reference)
    assert start == datetime(2026, 7, 13, tzinfo=timezone.utc)  # Monday
    assert start.weekday() == 0
    assert end == start.replace(day=20)


def test_monthly_bounds():
    reference = datetime(2026, 7, 15, tzinfo=timezone.utc)
    start, end = period_bounds(DashboardReportPeriod.MONTHLY, reference)
    assert start == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_monthly_bounds_roll_december_into_next_year():
    reference = datetime(2026, 12, 15, tzinfo=timezone.utc)
    start, end = period_bounds(DashboardReportPeriod.MONTHLY, reference)
    assert start == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_yearly_bounds():
    reference = datetime(2026, 7, 15, tzinfo=timezone.utc)
    start, end = period_bounds(DashboardReportPeriod.YEARLY, reference)
    assert start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_unknown_period_raises_value_error():
    with pytest.raises(ValueError):
        period_bounds("not-a-real-period", datetime.now(timezone.utc))


def test_non_utc_reference_is_normalized_to_utc():
    from datetime import timedelta

    plus_three = timezone(timedelta(hours=3))
    # 2026-07-15 01:00 +03:00 == 2026-07-14 22:00 UTC - the UTC day boundary,
    # not the +03:00 local day boundary, is what determines the DAILY bucket.
    reference = datetime(2026, 7, 15, 1, 0, tzinfo=plus_three)
    start, end = period_bounds(DashboardReportPeriod.DAILY, reference)
    assert start == datetime(2026, 7, 14, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 15, tzinfo=timezone.utc)


def test_dashboard_and_paper_trading_report_period_enums_are_interchangeable():
    # Both packages' independent ReportPeriod enums share the same
    # string values, so this shared function works identically
    # regardless of which caller's enum type is passed in - proving the
    # "no dependency on either caller" claim in this module's docstring.
    reference = datetime(2026, 7, 15, tzinfo=timezone.utc)
    for dashboard_period, paper_trading_period in zip(DashboardReportPeriod, PaperTradingReportPeriod):
        assert period_bounds(dashboard_period, reference) == period_bounds(paper_trading_period, reference)
