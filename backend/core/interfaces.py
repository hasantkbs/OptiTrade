"""
OptiTrade — Shared Structural Interfaces
===========================================
``typing.Protocol`` definitions describing the collaborator contracts
``core.hybrid_engine.HybridTradingEngine`` depends on. These formalize the
duck-typed dependency-injection shape the engine already used (constructor
parameters accepting concrete classes) without changing any behavior —
Protocols are structurally checked by static type checkers and are not
enforced at runtime, so existing call sites keep working unchanged.

Introduced ahead of the future Decision Engine consolidation (see
``docs/architecture/gap-analysis.md``, section 1) so later work has a
stable interface to converge the existing engines onto, instead of
re-deriving these shapes from scratch.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.ai_trader_persona import TradeRecommendation
from core.regime_scanner import MarketRegime, ScannedSymbol
from core.risk_manager import RiskLevels


@runtime_checkable
class RegimeScannerProtocol(Protocol):
    """Contract for the scanning layer (``core.regime_scanner.MarketRegimeScanner``)."""

    def scan_and_filter(self, symbols: List[str]) -> List[ScannedSymbol]:
        ...


@runtime_checkable
class TimeframeAnalyzerProtocol(Protocol):
    """Contract for the analysis layer (``core.mtf_analyzer.MultiTimeframeAnalyzer``)."""

    def analyze(self, symbol: str) -> Optional[Dict[str, Any]]:
        ...


@runtime_checkable
class RiskManagerProtocol(Protocol):
    """Contract for the risk layer (``core.risk_manager.DynamicRiskManager``)."""

    def calculate(self, entry_price: float, atr: float) -> RiskLevels:
        ...


@runtime_checkable
class NewsSentimentProtocol(Protocol):
    """Contract for the news-sentiment adapter (``core.news_adapter.NewsSentimentAdapter``)."""

    def get_sentiment(self, symbol: str) -> Optional[Dict[str, Any]]:
        ...


@runtime_checkable
class TraderPersonaProtocol(Protocol):
    """Contract for the recommendation layer (``core.ai_trader_persona.AITraderPersona``)."""

    def generate_recommendation(
        self,
        symbol: str,
        market_regime: MarketRegime,
        analysis: Dict[str, Any],
        risk: RiskLevels,
        news_sentiment: Optional[Dict[str, Any]] = None,
    ) -> TradeRecommendation:
        ...
