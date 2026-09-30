"""OptiTrade Analytics & Dashboard Platform — Alert dashboard."""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from dashboard.config import DashboardConfig
from dashboard.models import AlertDashboardView, TriggerEventSnapshot
from dashboard.repository import DashboardRepository
from watchlist.repository import WatchlistRepository

logger = logging.getLogger(__name__)
_MODULE = "dashboard.alert_dashboard"
_COMPONENT = "dashboard"


class AlertDashboardService:
    def __init__(
        self,
        repository: DashboardRepository,
        watchlist_repository: Optional[WatchlistRepository] = None,
        config: Optional[DashboardConfig] = None,
    ) -> None:
        self._repository = repository
        self._watchlist_repository = watchlist_repository or WatchlistRepository()
        self._config = config or DashboardConfig.from_env()

    def build(self, owner: Optional[str] = None) -> AlertDashboardView:
        started_at = time.perf_counter()
        alerts = self._watchlist_repository.list_alerts(owner=owner)
        alerts_by_id = {alert.id: alert for alert in alerts}
        active_count = sum(1 for alert in alerts if alert.enabled)

        since = datetime.now(timezone.utc) - timedelta(hours=24)
        history_rows = self._repository.list_alert_triggers(limit=self._config.recent_history_limit)
        if owner is not None:
            history_rows = [row for row in history_rows if row["alert_id"] in alerts_by_id]

        recently_fired = [
            TriggerEventSnapshot(
                alert_id=row["alert_id"], symbol=alerts_by_id.get(row["alert_id"]).symbol if row["alert_id"] in alerts_by_id else None,
                message=row["message"], triggered_at=row["triggered_at"],
            )
            for row in history_rows
        ]
        fired_last_24h = sum(1 for row in history_rows if row["triggered_at"] >= since)

        trigger_frequency_by_type: Counter = Counter()
        for row in history_rows:
            alert = alerts_by_id.get(row["alert_id"])
            if alert is not None:
                trigger_frequency_by_type[alert.alert_type.value] += 1

        view = AlertDashboardView(
            active_alerts=active_count, fired_last_24h=fired_last_24h, recently_fired=recently_fired,
            trigger_frequency_by_type=dict(trigger_frequency_by_type),
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, owner=owner,
        )
        return view
