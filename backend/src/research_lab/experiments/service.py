"""OptiTrade Research Lab — experiment management service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from research_lab.experiments.lifecycle import validate_transition
from research_lab.experiments.repository import ExperimentRepository
from research_lab.hypothesis.service import HypothesisRegistry
from research_lab.models import Experiment, ExperimentStatus

logger = logging.getLogger(__name__)


class ExperimentService:
    """Manages the experiment lifecycle. Every experiment must begin
    with a written hypothesis - `create()` requires one and registers
    it via `HypothesisRegistry` before the experiment itself is
    persisted."""

    def __init__(
        self,
        repository: Optional[ExperimentRepository] = None,
        hypothesis_registry: Optional[HypothesisRegistry] = None,
    ) -> None:
        self.repository = repository or ExperimentRepository()
        self.hypothesis_registry = hypothesis_registry or HypothesisRegistry()

    def create(self, name: str, author: str, hypothesis_statement: str, description: str = "") -> Experiment:
        hypothesis = self.hypothesis_registry.register(hypothesis_statement)
        experiment = Experiment(
            name=name, description=description, hypothesis_id=hypothesis.id, author=author,
            status=ExperimentStatus.DRAFT,
        )
        experiment.id = self.repository.save(experiment)
        log_event(
            logger, component="research_lab", module="research_lab.experiments.service", operation="create",
            status=STATUS_SUCCESS, experiment_id=experiment.id, hypothesis_id=hypothesis.id,
        )
        return experiment

    def get(self, experiment_id: int) -> Optional[Experiment]:
        return self.repository.get(experiment_id)

    def list_by_status(self, status: Optional[ExperimentStatus] = None, limit: int = 100) -> List[Experiment]:
        return self.repository.list_by_status(status, limit)

    def transition(self, experiment_id: int, target_status: ExperimentStatus) -> Experiment:
        experiment = self.repository.get(experiment_id)
        if experiment is None:
            raise ValueError(f"no experiment with id {experiment_id}")

        validate_transition(experiment.status, target_status)
        updated_at = datetime.now(timezone.utc)
        self.repository.update_status(experiment_id, target_status, updated_at)

        log_event(
            logger, component="research_lab", module="research_lab.experiments.service", operation="transition",
            status=STATUS_SUCCESS, experiment_id=experiment_id,
            from_status=experiment.status.value, to_status=target_status.value,
        )
        experiment.status = target_status
        experiment.updated_at = updated_at
        return experiment
