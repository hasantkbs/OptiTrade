"""
OptiTrade Fundamental Engine.

Standalone voting engine consuming only Feature Store data (see
`feature_adapter.py`), organized into six independent analyzer modules
(valuation, growth, profitability, financial_health, cashflow, quality).
Satisfies `decision_engine.interfaces.VotingEngineProtocol`.

Self-registers a lazily-initialized instance into
`engine_registry.registry.default_registry` on import — safe because
`FundamentalEngine` defers all I/O (Feature Store construction, database
connections) until `analyze()`/`vote()` is actually called.
"""
from engines.fundamental.engine import FundamentalEngine
from engines.fundamental.models import AnalyzerResult, FundamentalAnalysisResult, FundamentalExecutionMetadata

__all__ = ["FundamentalEngine", "AnalyzerResult", "FundamentalAnalysisResult", "FundamentalExecutionMetadata"]

from engine_registry.exceptions import DuplicateEngineError
from engine_registry.registry import default_registry

try:
    default_registry.register(FundamentalEngine())
except DuplicateEngineError:
    # Re-importing this module must not raise - the engine is already
    # registered. Any OTHER exception here (e.g. IncompatibleEngineError)
    # is a real bug and must propagate.
    pass
