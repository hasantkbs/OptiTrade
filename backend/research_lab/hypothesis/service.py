"""OptiTrade Research Lab — Hypothesis Registry service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from research_lab.hypothesis.repository import HypothesisRepository
from research_lab.models import Hypothesis, HypothesisOutcome

logger = logging.getLogger(__name__)


class HypothesisRegistry:
    """Registers and resolves hypotheses. Deliberately exposes no
    delete method - a hypothesis, once written, is never removed."""

    def __init__(self, repository: Optional[HypothesisRepository] = None) -> None:
        self.repository = repository or HypothesisRepository()

    def register(self, statement: str) -> Hypothesis:
        hypothesis = Hypothesis(statement=statement)
        hypothesis.id = self.repository.save(hypothesis)
        log_event(
            logger, component="research_lab", module="research_lab.hypothesis.service",
            operation="register", status=STATUS_SUCCESS, hypothesis_id=hypothesis.id,
        )
        return hypothesis

    def resolve(self, hypothesis_id: int, outcome: HypothesisOutcome, evidence: List[str]) -> Hypothesis:
        resolved_at = datetime.now(timezone.utc)
        self.repository.update_outcome(hypothesis_id, outcome, evidence, resolved_at)
        log_event(
            logger, component="research_lab", module="research_lab.hypothesis.service",
            operation="resolve", status=STATUS_SUCCESS, hypothesis_id=hypothesis_id, outcome=outcome.value,
        )
        return self.repository.get(hypothesis_id)

    def get(self, hypothesis_id: int) -> Optional[Hypothesis]:
        return self.repository.get(hypothesis_id)

    def list_by_outcome(self, outcome: Optional[HypothesisOutcome] = None, limit: int = 100) -> List[Hypothesis]:
        return self.repository.list_by_outcome(outcome, limit)
