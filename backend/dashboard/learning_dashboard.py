"""
OptiTrade Analytics & Dashboard Platform — Learning dashboard.

Engine rankings/drift/calibration reuse `learning/` directly (the
package that owns these metrics). "Live version" for promotion-candidate
comparison comes from `dashboard/repository.py`'s raw-SQL read of
`ml_training_model_registry` (never a Python import of `ml_training`) -
engines with no matching registry entry (non-ML engines like Technical/
Fundamental/News) are simply skipped for that one field, since
promotion candidacy is inherently a versioned-model concept.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from dashboard.config import DashboardConfig
from dashboard.models import (
    CalibrationHistoryPoint,
    EngineRanking,
    LearningDashboardView,
    LearningSampleSnapshot,
)
from dashboard.repository import DashboardRepository
from decision_engine.models import Prediction
from learning.models import DriftType, RollingWindow
from learning.persistence import LearningRepository
from learning.service import LearningService

logger = logging.getLogger(__name__)
_MODULE = "dashboard.learning_dashboard"
_COMPONENT = "dashboard"

_DRIFT_ALERT_TYPES = (DriftType.DEGRADING, DriftType.UNSTABLE)


class LearningDashboardService:
    def __init__(
        self,
        repository: DashboardRepository,
        learning_service: Optional[LearningService] = None,
        learning_repository: Optional[LearningRepository] = None,
        config: Optional[DashboardConfig] = None,
    ) -> None:
        self._repository = repository
        self._learning_repository = learning_repository or LearningRepository()
        self._learning_service = learning_service or LearningService(repository=self._learning_repository)
        self._config = config or DashboardConfig.from_env()

    def build(self, ranking_window: RollingWindow = RollingWindow.THIRTY_DAY) -> LearningDashboardView:
        started_at = time.perf_counter()
        engines = self._learning_repository.distinct_engines()

        rankings = self._engine_rankings(engines, ranking_window)
        drift_alerts = self._drift_alerts(engines)
        calibration_history = self._calibration_history(engines)
        promotion_candidates = self._promotion_candidates(engines, ranking_window)
        recent_samples = [
            LearningSampleSnapshot(
                symbol=row["symbol"], source=row["source"], decision=Prediction(row["decision"]),
                confidence=row["confidence"], decided_at=row["decided_at"], evaluated=row["evaluated"],
                correct=row["correct"],
            )
            for row in self._repository.list_recent_learning_samples(limit=self._config.recent_history_limit)
        ]

        view = LearningDashboardView(
            engine_rankings=rankings, recent_samples=recent_samples, promotion_candidates=promotion_candidates,
            drift_alerts=drift_alerts, calibration_history=calibration_history,
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, engine_count=len(engines),
        )
        return view

    def _engine_rankings(self, engines: List[tuple], window: RollingWindow) -> List[EngineRanking]:
        rows = []
        for engine_name, engine_version in engines:
            metrics = self._learning_service.get_accuracy(engine_name, engine_version, window)
            if metrics is None:
                continue
            weight_update = self._learning_repository.get_latest_weight_update(engine_name, engine_version)
            rows.append((engine_name, engine_version, metrics.accuracy, weight_update.new_weight if weight_update else None))

        rows.sort(key=lambda row: row[2], reverse=True)
        return [
            EngineRanking(engine_name=name, engine_version=version, accuracy=accuracy, current_weight=weight, rank=rank)
            for rank, (name, version, accuracy, weight) in enumerate(rows, start=1)
        ]

    def _drift_alerts(self, engines: List[tuple]) -> list:
        alerts = []
        for engine_name, engine_version in engines:
            signals = self._learning_repository.get_recent_drift_signals(engine_name, engine_version, limit=5)
            alerts.extend(signal for signal in signals if signal.drift_type in _DRIFT_ALERT_TYPES)
        return alerts

    def _calibration_history(self, engines: List[tuple]) -> List[CalibrationHistoryPoint]:
        points = []
        for engine_name, engine_version in engines:
            for window in RollingWindow:
                metrics = self._learning_service.get_accuracy(engine_name, engine_version, window)
                if metrics is None:
                    continue
                points.append(
                    CalibrationHistoryPoint(
                        engine_name=engine_name, engine_version=engine_version, window=window,
                        calibration_error=metrics.calibration_error,
                        confidence_reliability=metrics.confidence_reliability, computed_at=metrics.computed_at,
                    )
                )
        return points

    def _promotion_candidates(self, engines: List[tuple], window: RollingWindow) -> list:
        candidates = []
        seen_engine_names = {engine_name for engine_name, _ in engines}
        for engine_name in seen_engine_names:
            live_version = self._repository.get_active_version_for_engine(engine_name)
            if live_version is None:
                continue
            candidates.extend(self._learning_service.promotion_candidates(engine_name, live_version, window=window))
        return candidates
