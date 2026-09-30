"""OptiTrade Analytics & Dashboard Platform — system overview."""
from __future__ import annotations

import logging
import time
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from dashboard.models import LearningStatus, OverviewMetrics
from dashboard.repository import DashboardRepository
from learning.persistence import LearningRepository

logger = logging.getLogger(__name__)
_MODULE = "dashboard.overview"
_COMPONENT = "dashboard"


class OverviewDashboardService:
    """`active_engines` defaults to a proxy - the count of distinct
    engines Continuous Learning has ever observed - unless the caller
    injects the live `engine_registry.EngineRegistry`/
    `model_serving.PredictionService` main.py already constructs at
    startup, in which case the real enabled/active count is used."""

    def __init__(
        self,
        repository: DashboardRepository,
        learning_repository: Optional[LearningRepository] = None,
        engine_registry=None,
        model_serving=None,
    ) -> None:
        self._repository = repository
        self._learning_repository = learning_repository or LearningRepository()
        self._engine_registry = engine_registry
        self._model_serving = model_serving

    def build(self) -> OverviewMetrics:
        started_at = time.perf_counter()

        learning_status = LearningStatus(
            engines_tracked=len(self._learning_repository.distinct_engines()),
            total_samples=self._repository.count_learning_samples(),
            pending_samples=self._repository.count_pending_learning_samples(),
            last_evaluated_at=self._repository.get_last_evaluated_at(),
        )

        metrics = OverviewMetrics(
            total_users=self._repository.count_users(),
            active_users=self._repository.count_active_users(),
            total_portfolios=self._repository.count_portfolios(),
            total_watchlists=self._repository.count_watchlists(),
            total_alerts=self._repository.count_alerts(),
            total_paper_accounts=self._repository.count_paper_accounts(),
            total_models=self._repository.count_ml_models(),
            active_engines=self._active_engine_count(learning_status),
            learning_status=learning_status,
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return metrics

    def _active_engine_count(self, learning_status: LearningStatus) -> int:
        if self._engine_registry is not None or self._model_serving is not None:
            count = 0
            if self._engine_registry is not None:
                count += len(self._engine_registry.all_enabled())
            if self._model_serving is not None:
                count += len(self._model_serving.get_active_engines())
            return count
        return learning_status.engines_tracked
