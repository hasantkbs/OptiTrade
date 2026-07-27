"""OptiTrade Research Lab — backtesting service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from learning.persistence import LearningRepository
from research_lab.backtesting.engine import BacktestEngine
from research_lab.backtesting.repository import BacktestRepository
from research_lab.config import ResearchLabConfig
from research_lab.models import BacktestMethod, BacktestResult

logger = logging.getLogger(__name__)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


class BacktestService:
    """Sources the historical return series straight from Continuous
    Learning's already-evaluated engine outcomes (never re-executes
    the engine, never touches production inference), runs the
    requested backtest method, and persists the result."""

    def __init__(
        self,
        learning_repository: Optional[LearningRepository] = None,
        repository: Optional[BacktestRepository] = None,
        engine: Optional[BacktestEngine] = None,
        config: Optional[ResearchLabConfig] = None,
    ) -> None:
        self.learning_repository = learning_repository or LearningRepository()
        self.repository = repository or BacktestRepository()
        self.config = config or ResearchLabConfig.from_env()
        self.engine = engine or BacktestEngine(config=self.config)

    def run(
        self,
        method: BacktestMethod,
        engine_name: str,
        engine_version: str,
        since: Optional[datetime] = None,
        experiment_id: Optional[int] = None,
    ) -> BacktestResult:
        since = since or _EPOCH
        outcomes = self.learning_repository.get_engine_outcomes(engine_name, engine_version, since=since)
        series = sorted(
            [(o.decided_at, o.actual_return) for o in outcomes if o.evaluated and o.actual_return is not None],
            key=lambda pair: pair[0],
        )

        result = self.engine.run(method, engine_name, engine_version, series, experiment_id=experiment_id)
        result.id = self.repository.save(result)

        log_event(
            logger, component="research_lab", module="research_lab.backtesting.service", operation="run",
            status=STATUS_SUCCESS, engine_name=engine_name, engine_version=engine_version,
            method=method.value, fold_count=len(result.folds), sample_count=result.sample_count,
        )
        return result
