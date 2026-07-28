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
from feature_store.service import FeatureStoreService
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
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.config = config or PipelineConfig.from_env()
        self.feature_store = feature_store or FeatureStoreService()
        self.engine_registry = engine_registry or default_registry
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
        return self.pipeline.run(symbol.upper())
