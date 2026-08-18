"""
OptiTrade Analytics & Dashboard Platform — Decision Engine dashboard.

Engine accuracy/weights/drift come straight from `learning/` (the sole
owner of those metrics - `decision_engine` itself only stores decision
execution history). Calibration is model-level, read directly from
`ml_training_calibration_results` via `dashboard/repository.py` (see its
module docstring for why this is a raw-SQL read rather than a Python
import of `ml_training`). Regime distribution reuses
`core.regime_scanner.MarketRegimeScanner` over a caller-supplied symbol
universe - there is no cross-symbol regime aggregate anywhere else in
the codebase.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from core.regime_scanner import MarketRegimeScanner
from core.structured_logging import STATUS_SUCCESS, log_event
from dashboard.analytics import build_time_series
from dashboard.config import DashboardConfig
from dashboard.models import CalibrationSnapshot, EngineAccuracySnapshot, EngineDashboardView
from dashboard.repository import DashboardRepository
from learning.models import RollingWindow
from learning.persistence import LearningRepository
from learning.service import LearningService

logger = logging.getLogger(__name__)
_MODULE = "dashboard.engine_dashboard"
_COMPONENT = "dashboard"


class EngineDashboardService:
    def __init__(
        self,
        repository: DashboardRepository,
        learning_service: Optional[LearningService] = None,
        learning_repository: Optional[LearningRepository] = None,
        regime_scanner: Optional[MarketRegimeScanner] = None,
        config: Optional[DashboardConfig] = None,
    ) -> None:
        self._repository = repository
        self._learning_repository = learning_repository or LearningRepository()
        self._learning_service = learning_service or LearningService(repository=self._learning_repository)
        self._regime_scanner = regime_scanner or MarketRegimeScanner()
        self._config = config or DashboardConfig.from_env()

    def build(self, symbol: Optional[str] = None, regime_symbols: Optional[List[str]] = None) -> EngineDashboardView:
        started_at = time.perf_counter()

        engines = [
            self._engine_snapshot(engine_name, engine_version)
            for engine_name, engine_version in self._learning_repository.distinct_engines()
        ]

        calibration = [
            CalibrationSnapshot(
                model_id=row["model_id"], method=row["method"],
                calibration_error_before=row["calibration_error_before"],
                calibration_error_after=row["calibration_error_after"], computed_at=row["computed_at"],
            )
            for row in self._repository.list_calibration_results(limit=self._config.recent_history_limit)
        ]

        executions = self._repository.list_recent_decision_executions(
            symbol=symbol, limit=self._config.recent_history_limit,
        )
        confidence_history = build_time_series(
            "confidence", [(row["timestamp"], row["confidence"]) for row in executions]
        ).points
        expected_return_history = build_time_series(
            "expected_return", [(row["timestamp"], row["expected_return"]) for row in executions]
        ).points

        regime_distribution = {}
        if regime_symbols:
            for scanned in self._regime_scanner.scan(regime_symbols):
                regime_distribution[scanned.regime.value] = regime_distribution.get(scanned.regime.value, 0) + 1

        view = EngineDashboardView(
            engines=engines, calibration=calibration,
            drift_signals=[engine.latest_drift for engine in engines if engine.latest_drift is not None],
            confidence_history=confidence_history, regime_distribution=regime_distribution,
            expected_return_history=expected_return_history,
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, engine_count=len(engines),
        )
        return view

    def _engine_snapshot(self, engine_name: str, engine_version: str) -> EngineAccuracySnapshot:
        accuracy_by_window = self._learning_service.get_accuracy_for_windows(
            engine_name, engine_version, list(RollingWindow)
        )

        weight_update = self._learning_repository.get_latest_weight_update(engine_name, engine_version)
        drift_signals = self._learning_repository.get_recent_drift_signals(engine_name, engine_version, limit=1)

        return EngineAccuracySnapshot(
            engine_name=engine_name, engine_version=engine_version, accuracy_by_window=accuracy_by_window,
            current_weight=weight_update.new_weight if weight_update else None,
            latest_drift=drift_signals[0] if drift_signals else None,
        )
