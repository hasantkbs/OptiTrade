"""
OptiTrade Pipeline — DI facade / singleton wiring.

The single entry point `main.py` depends on. Constructing this once
(not per-request) and reusing it across every request is what
satisfies "reuse Feature Store cache" / "never duplicate expensive
calculations": the three voting engines here are the SAME
already-self-registered singleton instances every other part of this
backend shares (`engine_registry.registry.default_registry`), each
lazily constructing its own Feature Store connection exactly once, on
first use, for the lifetime of the process - not per request.

Model Serving integration (requirement 9 of the Model Serving
Platform): every currently-served DIRECTION model is folded into this
call's own engine list on each `run()` call, alongside the fixed
Technical/Fundamental/News three - `Pipeline` itself (frozen, untouched)
has no idea an ML model is any different from those three, and
`pipeline.executor.ParallelEngineExecutor` runs all of them concurrently
with zero duplicated logic. Resolving the engine list fresh on every
call (rather than once at construction, like the fixed three) is what
makes "automatic reload"/"version routing" (`model_serving`'s own
requirements) actually reach an already-running process - the
per-request cost is bounded by `model_serving`'s own Redis cache, not a
Postgres round trip every time. This resolved list is passed straight
into `Pipeline.run(symbol, engines=...)` as a per-call argument, never
stashed on shared `self.pipeline` state - `PipelineService`/`Pipeline`
are process-wide singletons main.py runs concurrent requests through
(a 16-thread executor pool), so per-request engine composition has to
stay on that call's own stack (see `pipeline.context.PipelineContext.
engines`), not shared mutable instance state two in-flight requests
could otherwise race on. Shadow inference for the same symbol is then
submitted in the background (see `model_serving.shadow`) - it never
affects the response just returned.
"""
from __future__ import annotations

import logging
from typing import List, Optional

# Imported for self-registration side effects only - guarantees these
# engines are present in default_registry regardless of what else has
# been imported by the time this module loads.
import engines.fundamental  # noqa: F401
import engines.news  # noqa: F401
import engines.technical  # noqa: F401
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.interfaces import VotingEngineProtocol
from engine_registry.registry import EngineRegistry, default_registry
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from model_serving.service import PredictionService
from pipeline.config import PipelineConfig
from pipeline.models import PipelineResponse
from pipeline.pipeline import Pipeline

logger = logging.getLogger(__name__)


class PipelineService:
    """Constructs (once) and runs the production pipeline. Intended to
    be a process-wide singleton - see `main.py`."""

    def __init__(
        self,
        pipeline: Optional[Pipeline] = None,
        engine_registry: Optional[EngineRegistry] = None,
        feature_store: Optional[FeatureStoreService] = None,
        model_serving: Optional[PredictionService] = None,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.config = config or PipelineConfig.from_env()
        self.feature_store = feature_store or get_default_feature_store_service()
        self.engine_registry = engine_registry or default_registry
        self.model_serving = model_serving or PredictionService()
        self.model_serving.warm_up()
        self.pipeline = pipeline or Pipeline(
            engines=self._resolve_engines(), feature_store=self.feature_store, config=self.config,
        )
        log_event(
            logger, component="pipeline", module="pipeline.service", operation="init",
            status=STATUS_SUCCESS, engine_count=len(self.pipeline.engines),
        )

    def _resolve_engines(self) -> List[VotingEngineProtocol]:
        names_and_versions = [
            ("TechnicalEngine", self.config.technical_engine_version),
            ("FundamentalEngine", self.config.fundamental_engine_version),
            ("NewsEngine", self.config.news_engine_version),
        ]
        resolved: List[VotingEngineProtocol] = []
        for name, version in names_and_versions:
            try:
                resolved.append(self.engine_registry.get(name, version))
            except Exception as exc:
                log_event(
                    logger, component="pipeline", module="pipeline.service", operation="resolve_engines",
                    status=STATUS_ERROR, engine_name=name, error_type=type(exc).__name__, level=logging.ERROR,
                )
        return resolved

    def run(self, symbol: str) -> PipelineResponse:
        symbol = symbol.upper()
        # Resolved fresh into a LOCAL variable and passed straight
        # through to this call's own `Pipeline.run(..., engines=...)` -
        # never assigned to `self.pipeline.engines` (shared singleton
        # state). `PipelineService`/`Pipeline` are process-wide
        # singletons reused across every concurrent request (see this
        # module's docstring); mutating shared state per request here
        # would let one request's engine composition leak into or get
        # clobbered by another's, since main.py runs requests through a
        # 16-thread executor pool. See PipelineContext.engines.
        engines = self._resolve_engines() + self._resolve_model_serving_engines()
        response = self.pipeline.run(symbol, engines=engines)
        self.model_serving.run_shadow_inference(symbol)
        return response

    def _resolve_model_serving_engines(self) -> List[VotingEngineProtocol]:
        try:
            return self.model_serving.get_active_engines()
        except Exception as exc:
            log_event(
                logger, component="pipeline", module="pipeline.service", operation="resolve_model_serving_engines",
                status=STATUS_ERROR, error_type=type(exc).__name__, level=logging.ERROR,
            )
            return []
