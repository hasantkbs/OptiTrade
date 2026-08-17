"""
OptiTrade Pipeline — production execution orchestrator.

Execution order: Load Features -> Technical/Fundamental/News Engines
(parallel) -> Decision Engine -> Explanation Engine -> Learning Tracker
-> API Response.

Deliberately does NOT call `decision_engine.service.DecisionEngine.
decide()` end-to-end - that method collects votes serially (a plain
for-loop with no timeout), which cannot satisfy this pipeline's
parallel-execution requirement. Instead this reuses every one of its
real computational/persistence building blocks directly -
`decision_engine.aggregation.aggregate_votes` (pure aggregation math),
`decision_engine.weighting.AccuracyWeightProvider` (Feature Store-backed
per-engine weights), `decision_engine.validation.validate_vote`
(already applied by `executor.py`), and
`decision_engine.repository.PostgresExecutionRepository` (the exact
same execution-history table `DecisionEngine.decide()` itself writes
to) - while owning the concurrent vote-collection orchestration itself
via `executor.ParallelEngineExecutor`.

Research Lab never executes here - nothing in this module imports
`research_lab` (enforced by `tests/test_research_isolation.py`).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.aggregation import aggregate_votes
from decision_engine.interfaces import ExecutionRepositoryProtocol, VotingEngineProtocol
from decision_engine.models import DecisionOutput
from decision_engine.weighting import AccuracyWeightProvider
from explanation_engine.service import ExplanationEngine
from feature_store.service import FeatureStoreService
from learning.service import LearningService
from pipeline.config import PipelineConfig
from pipeline.context import PipelineContext
from pipeline.executor import ParallelEngineExecutor
from pipeline.models import (
    EngineBreakdownItem,
    EngineExecutionStatus,
    PipelineMetadata,
    PipelineResponse,
    RiskAssessment,
)

logger = logging.getLogger(__name__)

_AGGREGATION_STRATEGY_VERSION = "pipeline_parallel_v1"


class Pipeline:
    """Dependency-injectable production pipeline. Every constructor
    parameter defaults to the real, config-driven implementation -
    matching the DI pattern established across every other package."""

    def __init__(
        self,
        engines: List[VotingEngineProtocol],
        feature_store: Optional[FeatureStoreService] = None,
        weight_provider: Optional[AccuracyWeightProvider] = None,
        execution_repository: Optional[ExecutionRepositoryProtocol] = None,
        explanation_engine: Optional[ExplanationEngine] = None,
        learning_service: Optional[LearningService] = None,
        executor: Optional[ParallelEngineExecutor] = None,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.config = config or PipelineConfig.from_env()
        self.engines = engines
        self.feature_store = feature_store or FeatureStoreService()

        from decision_engine.config import DecisionEngineConfig
        from decision_engine.repository import PostgresExecutionRepository

        self._decision_engine_config = DecisionEngineConfig.from_env()
        self.weight_provider = weight_provider or AccuracyWeightProvider(self.feature_store, self._decision_engine_config)
        self.execution_repository: ExecutionRepositoryProtocol = execution_repository or PostgresExecutionRepository()
        self.explanation_engine = explanation_engine or ExplanationEngine()
        self.learning_service = learning_service or LearningService()
        self.executor = executor or ParallelEngineExecutor(config=self.config)

    def run(self, symbol: str, engines: Optional[List[VotingEngineProtocol]] = None) -> PipelineResponse:
        """`engines`, when given, is this call's own engine composition -
        never stored on `self` (see PipelineContext.engines' docstring
        for why: `self.engines` is shared singleton state read
        concurrently by every in-flight request, `context.engines` is
        local to this call's stack). Falls back to the fixed set this
        `Pipeline` was constructed with when omitted, for callers (tests,
        ad-hoc scripts) that construct a `Pipeline` directly with a
        static engine list and never override it per call."""
        pipeline_started_at = time.perf_counter()
        context = PipelineContext(symbol=symbol, engines=engines if engines is not None else self.engines)

        self._load_features_stage(context)
        self._engines_stage(context, symbol)
        self._decision_stage(context, symbol)
        self._persist_decision(context.decision_output)
        self._explanation_stage(context, symbol)
        self._learning_stage(context)

        total_duration_ms = (time.perf_counter() - pipeline_started_at) * 1000
        response = self._build_response(context, total_duration_ms)

        log_event(
            logger, component="pipeline", module="pipeline.pipeline", operation="run", status=STATUS_SUCCESS,
            symbol=symbol, decision=context.decision_output.decision.value, confidence=context.decision_output.confidence,
            engines_succeeded=response.metadata.engines_succeeded, degraded=response.metadata.degraded,
            execution_time_ms=total_duration_ms,
        )
        return response

    # ── Stages ───────────────────────────────────────────────────────────

    def _load_features_stage(self, context: PipelineContext) -> None:
        started_at = time.perf_counter()
        try:
            self.feature_store.health_check()
        except Exception as exc:
            log_event(
                logger, component="pipeline", module="pipeline.pipeline", operation="load_features",
                status=STATUS_ERROR, symbol=context.symbol, error_type=type(exc).__name__, level=logging.WARNING,
            )
        context.record_stage("load_features", (time.perf_counter() - started_at) * 1000)

    def _engines_stage(self, context: PipelineContext, symbol: str) -> None:
        started_at = time.perf_counter()
        context.execution_results = self.executor.collect_votes(context.engines, symbol)
        context.record_stage("engines", (time.perf_counter() - started_at) * 1000)

    def _decision_stage(self, context: PipelineContext, symbol: str) -> None:
        started_at = time.perf_counter()
        votes = [
            result.vote for result in context.execution_results
            if result.status == EngineExecutionStatus.SUCCESS and result.vote is not None
        ]
        weights = {vote.engine_name: self._get_weight_safely(vote.engine_name, symbol) for vote in votes}
        aggregation = aggregate_votes(votes, weights)

        data_sufficiency = (len(votes) / len(context.engines)) if context.engines else 0.0

        context.decision_output = DecisionOutput(
            symbol=symbol,
            decision=aggregation.decision,
            confidence=aggregation.confidence,
            expected_return=aggregation.expected_return,
            expected_volatility=aggregation.expected_volatility,
            aggregation_strategy_version=_AGGREGATION_STRATEGY_VERSION,
            data_sufficiency=data_sufficiency,
            evidence=aggregation.evidence,
            engine_results=votes,
            timestamp=datetime.now(timezone.utc),
        )
        context.record_stage("decision", (time.perf_counter() - started_at) * 1000)

    def _get_weight_safely(self, engine_name: str, symbol: str) -> float:
        """`self.weight_provider.get_weight` was the only per-vote call
        in this stage with no failure isolation of its own - a Feature
        Store hiccup there would propagate out of `_decision_stage` and
        turn an otherwise-successful vote collection into a hard
        failure for the whole request. Every other stage in this class
        already degrades gracefully (log + continue) on an injected
        dependency's failure; this matches that same pattern rather than
        relying solely on `AccuracyWeightProvider.get_weight`'s own
        fallback (any `weight_provider` implementation is protected
        here, not just the real one)."""
        try:
            return self.weight_provider.get_weight(engine_name)
        except Exception as exc:
            log_event(
                logger, component="pipeline", module="pipeline.pipeline", operation="decision_weight_lookup",
                status=STATUS_ERROR, symbol=symbol, engine_name=engine_name, error_type=type(exc).__name__,
                level=logging.WARNING,
            )
            return self._decision_engine_config.default_accuracy_weight

    def _persist_decision(self, decision_output: Optional[DecisionOutput]) -> None:
        if decision_output is None:
            return
        try:
            self.execution_repository.save(decision_output)
        except Exception as exc:
            log_event(
                logger, component="pipeline", module="pipeline.pipeline", operation="persist_decision",
                status=STATUS_ERROR, symbol=decision_output.symbol, error_type=type(exc).__name__,
                level=logging.ERROR,
            )

    def _explanation_stage(self, context: PipelineContext, symbol: str) -> None:
        started_at = time.perf_counter()
        context.explanation = self.explanation_engine.explain(context.decision_output, symbol)
        context.record_stage("explanation", (time.perf_counter() - started_at) * 1000)

    def _learning_stage(self, context: PipelineContext) -> None:
        started_at = time.perf_counter()
        try:
            self.learning_service.record_decision(context.decision_output)
        except Exception as exc:
            log_event(
                logger, component="pipeline", module="pipeline.pipeline", operation="learning_tracker",
                status=STATUS_ERROR, symbol=context.symbol, error_type=type(exc).__name__, level=logging.ERROR,
            )
        context.record_stage("learning", (time.perf_counter() - started_at) * 1000)

    # ── Response building ────────────────────────────────────────────────

    def _build_response(self, context: PipelineContext, total_duration_ms: float) -> PipelineResponse:
        decision_output = context.decision_output
        engines_succeeded = sum(
            1 for result in context.execution_results if result.status == EngineExecutionStatus.SUCCESS
        )
        degraded = engines_succeeded < len(context.engines)

        return PipelineResponse(
            symbol=context.symbol,
            decision=decision_output.decision,
            confidence=decision_output.confidence,
            expected_return=decision_output.expected_return,
            expected_volatility=decision_output.expected_volatility,
            engine_breakdown=[self._to_breakdown_item(result) for result in context.execution_results],
            evidence=decision_output.evidence,
            risk=RiskAssessment(
                risk_level=self._risk_level(decision_output.expected_volatility),
                expected_volatility=decision_output.expected_volatility,
                data_sufficiency=decision_output.data_sufficiency,
            ),
            explanation=context.explanation.text if context.explanation is not None else "",
            metadata=PipelineMetadata(
                pipeline_version=self.config.pipeline_version,
                total_duration_ms=total_duration_ms,
                stage_durations_ms=context.stage_durations_ms,
                engines_available=len(context.engines),
                engines_succeeded=engines_succeeded,
                degraded=degraded,
                timestamp=decision_output.timestamp,
            ),
        )

    @staticmethod
    def _to_breakdown_item(result) -> EngineBreakdownItem:
        vote = result.vote
        return EngineBreakdownItem(
            engine_name=result.engine_name, engine_version=result.engine_version, status=result.status,
            prediction=vote.prediction if vote is not None else None,
            confidence=vote.confidence if vote is not None else None,
            expected_return=vote.expected_return if vote is not None else None,
            volatility=vote.volatility if vote is not None else None,
            evidence=vote.evidence if vote is not None else [],
        )

    def _risk_level(self, expected_volatility: float) -> str:
        magnitude = abs(expected_volatility)
        if magnitude < self.config.low_volatility_threshold_pct:
            return "LOW"
        if magnitude < self.config.high_volatility_threshold_pct:
            return "MEDIUM"
        return "HIGH"
