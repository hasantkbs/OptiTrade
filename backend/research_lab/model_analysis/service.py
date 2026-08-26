"""OptiTrade Research Lab — model analysis service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from learning.accuracy import window_start
from learning.config import LearningConfig
from learning.models import RollingWindow
from learning.persistence import LearningRepository
from research_lab.config import ResearchLabConfig
from research_lab.model_analysis import analyzer
from research_lab.model_analysis.repository import ModelAnalysisRepository
from research_lab.models import ModelAnalysisResult

logger = logging.getLogger(__name__)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


class ModelAnalysisService:
    """Reads already-evaluated engine outcomes straight from
    Continuous Learning's repository (never re-tracks anything itself)
    and produces/persists `ModelAnalysisResult`s."""

    def __init__(
        self,
        learning_repository: Optional[LearningRepository] = None,
        repository: Optional[ModelAnalysisRepository] = None,
        learning_config: Optional[LearningConfig] = None,
        config: Optional[ResearchLabConfig] = None,
    ) -> None:
        self.learning_repository = learning_repository or LearningRepository()
        self.repository = repository or ModelAnalysisRepository()
        self.learning_config = learning_config or LearningConfig.from_env()
        self.config = config or ResearchLabConfig.from_env()

    def analyze(
        self, engine_name: str, engine_version: str, window: RollingWindow, now: Optional[datetime] = None,
    ) -> ModelAnalysisResult:
        now = now or datetime.now(timezone.utc)
        since = window_start(window, now) or _EPOCH
        outcomes = self.learning_repository.get_engine_outcomes(engine_name, engine_version, since=since)

        result = analyzer.analyze(
            engine_name, engine_version, window, outcomes,
            learning_config=self.learning_config, risk_free_rate=self.config.risk_free_rate,
        )
        self.repository.save(result)

        log_event(
            logger, component="research_lab", module="research_lab.model_analysis.service", operation="analyze",
            status=STATUS_SUCCESS, engine_name=engine_name, engine_version=engine_version,
            window=window.value, sample_count=result.accuracy_metrics.sample_count,
        )
        return result

    def get_history(
        self, engine_name: str, engine_version: str, window: RollingWindow, limit: int = 10,
    ) -> List[ModelAnalysisResult]:
        return self.repository.get_history(engine_name, engine_version, window, limit)
