"""
OptiTrade News Engine.

Standalone voting engine that consumes news via `feature_adapter.py`,
organized into small pipeline-stage modules (providers, normalizer,
deduplicator, asset_resolver, sentiment, relevance, impact,
aggregator). Satisfies `decision_engine.interfaces.VotingEngineProtocol`.
Fully deterministic - never calls an LLM, never lets one vote.

Self-registers a lazily-initialized instance into
`engine_registry.registry.default_registry` on import - safe because
`NewsEngine` defers all I/O (Feature Store construction, database
connections, network calls) until `analyze()`/`vote()` is actually
called.
"""
from engines.news.engine import NewsEngine
from engines.news.models import NewsAnalysisResult, NewsEvidence, NewsExecutionMetadata

__all__ = ["NewsEngine", "NewsAnalysisResult", "NewsEvidence", "NewsExecutionMetadata"]

from engine_registry.exceptions import DuplicateEngineError
from engine_registry.registry import default_registry

try:
    default_registry.register(NewsEngine())
except DuplicateEngineError:
    # Re-importing this module must not raise - the engine is already
    # registered. Any OTHER exception here (e.g. IncompatibleEngineError)
    # is a real bug and must propagate.
    pass
