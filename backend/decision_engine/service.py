"""
OptiTrade Decision Engine — orchestrator.

Loads every registered voting engine, executes them, validates their
output, ignores invalid/failed responses, calculates accuracy-weighted
votes, and produces a single `DecisionOutput`. Every execution is
persisted for future learning. LLMs never participate here — voting
engines are purely statistical (see `decision_engine/models.py`).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.aggregation import aggregate_votes
from decision_engine.config import DecisionEngineConfig
from decision_engine.exceptions import NoValidVotesError
from decision_engine.interfaces import ExecutionRepositoryProtocol
from decision_engine.models import DecisionOutput, EngineVote
from decision_engine.registry import VotingEngineRegistry
from decision_engine.repository import PostgresExecutionRepository
from decision_engine.validation import validate_vote
from decision_engine.weighting import AccuracyWeightProvider
from feature_store.service import FeatureStoreService, get_default_feature_store_service

logger = logging.getLogger(__name__)


class DecisionEngine:
    """Dependency-injectable orchestrator over the voting engine registry,
    the accuracy-weight provider (Feature Store-backed), and the execution
    repository — matching the DI pattern established for
    `core.hybrid_engine.HybridTradingEngine` and
    `feature_store.service.FeatureStoreService`."""

    def __init__(
        self,
        registry: Optional[VotingEngineRegistry] = None,
        feature_store: Optional[FeatureStoreService] = None,
        execution_repository: Optional[ExecutionRepositoryProtocol] = None,
        config: Optional[DecisionEngineConfig] = None,
    ) -> None:
        # `registry` uses an explicit `is not None` check rather than `or`:
        # VotingEngineRegistry defines __len__, so an empty-but-validly-
        # provided registry (0 engines registered yet) is falsy in Python
        # and `registry or VotingEngineRegistry()` would silently discard
        # it in favor of a brand new, disconnected instance - breaking any
        # caller that registers engines onto it after construction.
        self.registry = registry if registry is not None else VotingEngineRegistry()
        self.config = config or DecisionEngineConfig.from_env()
        self.feature_store = feature_store or get_default_feature_store_service()
        self.execution_repository: ExecutionRepositoryProtocol = (
            execution_repository or PostgresExecutionRepository()
        )
        self.weight_provider = AccuracyWeightProvider(self.feature_store, self.config)

    def decide(self, symbol: str, strict: bool = False) -> DecisionOutput:
        """Runs every registered voting engine for `symbol` and returns a
        single aggregated `DecisionOutput`.

        With `strict=False` (the default), a symbol with zero valid votes
        still produces a DecisionOutput — a neutral HOLD with
        confidence=0.0 and data_sufficiency=0.0 — rather than raising, so
        one badly-behaved or not-yet-registered engine can never crash a
        caller. With `strict=True`, `NoValidVotesError` is raised instead,
        for callers (e.g. a future monitoring/learning job) that need to
        detect a total voting failure explicitly.
        """
        started_at = time.perf_counter()
        registered = self.registry.all()
        votes = self._collect_valid_votes(symbol, registered)

        if not votes and strict:
            raise NoValidVotesError(symbol)

        weights = {vote.engine_name: self.weight_provider.get_weight(vote.engine_name) for vote in votes}
        aggregation = aggregate_votes(votes, weights)

        data_sufficiency = (len(votes) / len(registered)) if registered else 0.0

        output = DecisionOutput(
            symbol=symbol,
            decision=aggregation.decision,
            confidence=aggregation.confidence,
            expected_return=aggregation.expected_return,
            expected_volatility=aggregation.expected_volatility,
            aggregation_strategy_version=self.config.aggregation_strategy_version,
            data_sufficiency=data_sufficiency,
            evidence=aggregation.evidence,
            engine_results=votes,
            timestamp=datetime.now(timezone.utc),
        )

        self._persist(output)

        log_event(
            logger,
            component="decision_engine",
            module="decision_engine.service",
            operation="decide",
            status=STATUS_SUCCESS,
            symbol=symbol,
            decision=output.decision.value,
            confidence=output.confidence,
            valid_votes=len(votes),
            registered_engines=len(registered),
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return output

    def _collect_valid_votes(self, symbol: str, engines: list) -> List[EngineVote]:
        votes: List[EngineVote] = []
        for engine in engines:
            engine_name = getattr(engine, "engine_name", type(engine).__name__)
            try:
                vote = engine.vote(symbol)
            except Exception as exc:
                log_event(
                    logger,
                    component="decision_engine",
                    module="decision_engine.service",
                    operation="collect_vote",
                    status=STATUS_ERROR,
                    symbol=symbol,
                    engine_name=engine_name,
                    error_type=type(exc).__name__,
                    level=logging.WARNING,
                )
                continue

            result = validate_vote(vote)
            if not result.is_valid:
                log_event(
                    logger,
                    component="decision_engine",
                    module="decision_engine.service",
                    operation="collect_vote",
                    status=STATUS_ERROR,
                    symbol=symbol,
                    engine_name=engine_name,
                    error_type="InvalidVoteError",
                    level=logging.WARNING,
                )
                continue

            votes.append(vote)
        return votes

    def _persist(self, output: DecisionOutput) -> None:
        try:
            self.execution_repository.save(output)
        except Exception as exc:
            # Persistence failure must not invalidate an otherwise-valid
            # decision the caller is about to receive.
            log_event(
                logger,
                component="decision_engine",
                module="decision_engine.service",
                operation="persist",
                status=STATUS_ERROR,
                symbol=output.symbol,
                error_type=type(exc).__name__,
                level=logging.ERROR,
            )
