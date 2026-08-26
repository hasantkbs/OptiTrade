"""
OptiTrade — shared reporting period boundary computation.

Both `dashboard/reports.py` and `paper_trading/reports.py` need to turn
a DAILY/WEEKLY/MONTHLY/YEARLY period into a concrete `[start, end)` UTC
datetime range with the same calendar semantics (midnight-aligned day,
Monday-start week, calendar month, calendar year) - this is the one
canonical implementation both now share instead of two independently
maintained copies.

Accepts any period value whose `.value` is `"daily"`/`"weekly"`/
`"monthly"`/`"yearly"` (both `dashboard.models.ReportPeriod` and
`paper_trading.models.ReportPeriod` satisfy this, being separate
`(str, Enum)` classes with matching members) rather than importing
either package's own enum - this module has no dependency on either
caller, in keeping with it being genuinely shared, neutral logic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple

_DAILY = "daily"
_WEEKLY = "weekly"
_MONTHLY = "monthly"
_YEARLY = "yearly"


def period_bounds(period, reference: datetime) -> Tuple[datetime, datetime]:
    """`period` is a DAILY/WEEKLY/MONTHLY/YEARLY-valued enum member (or
    a plain matching string) - only its string value is inspected."""
    period_value = getattr(period, "value", period)
    reference = reference.astimezone(timezone.utc)
    if period_value == _DAILY:
        start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif period_value == _WEEKLY:
        start = (reference - timedelta(days=reference.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
    elif period_value == _MONTHLY:
        start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    elif period_value == _YEARLY:
        start = reference.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
    else:
        raise ValueError(f"unknown report period {period!r}")
    return start, end
