"""
OptiTrade Technical Engine.

Standalone voting engine consuming only Feature Store data (see
`feature_adapter.py`), organized into six independent analyzer modules
(trend, momentum, oscillator, volatility, volume, market_structure).
Satisfies `decision_engine.interfaces.VotingEngineProtocol`.

Self-registers a lazily-initialized instance into
`engine_registry.registry.default_registry` on import — safe because
`TechnicalEngine` defers all I/O (Feature Store construction, database
connections) until `analyze()`/`vote()` is actually called.
"""
from engines.technical.engine import TechnicalEngine
from engines.technical.models import AnalyzerResult, TechnicalAnalysisResult, TechnicalExecutionMetadata

__all__ = ["TechnicalEngine", "AnalyzerResult", "TechnicalAnalysisResult", "TechnicalExecutionMetadata"]

from engine_registry.exceptions import DuplicateEngineError
from engine_registry.registry import default_registry

try:
    default_registry.register(TechnicalEngine())
except DuplicateEngineError:
    # Re-importing this module (e.g. repeated test collection, or a
    # second discover_engines() pass) must not raise - the engine is
    # already registered. Any OTHER exception here (e.g.
    # IncompatibleEngineError) is a real bug and must propagate.
    pass
