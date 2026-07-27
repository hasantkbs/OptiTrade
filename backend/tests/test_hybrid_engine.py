"""
Characterization tests for core/hybrid_engine.py (HybridTradingEngine),
written as part of Sprint 1 Task 6's structural refactor: retyping the
engine's constructor parameters from concrete classes to the new
core.interfaces Protocols.

These tests prove two things:
1. HybridTradingEngine's runtime behavior (caching, regime-filtered
   iteration, per-symbol error isolation, exception fallback) is
   unchanged by the retyping - exercised here via fakes that satisfy the
   new Protocols structurally, injected through the exact same
   constructor parameters that existed before this task.
2. The concrete production classes (MarketRegimeScanner,
   MultiTimeframeAnalyzer, DynamicRiskManager, NewsSentimentAdapter,
   AITraderPersona) still satisfy the new Protocols - i.e. existing
   callers that construct HybridTradingEngine with real instances (or
   with no arguments at all, relying on the constructor's own defaults)
   continue to work unmodified. This is checked via `issubclass()`
   against the classes themselves (not `isinstance()` on instances), so
   it requires no network calls or API keys - AITraderPersona's
   constructor builds a Groq client that may need credentials, which this
   check deliberately avoids needing.
"""
from typing import Any, Dict, List, Optional, Tuple

from core.ai_trader_persona import AITraderPersona, TradeRecommendation
from core.hybrid_engine import HybridTradingEngine
from core.interfaces import (
    NewsSentimentProtocol,
    RegimeScannerProtocol,
    RiskManagerProtocol,
    TimeframeAnalyzerProtocol,
    TraderPersonaProtocol,
)
from core.mtf_analyzer import MultiTimeframeAnalyzer
from core.news_adapter import NewsSentimentAdapter
from core.regime_scanner import MarketRegime, MarketRegimeScanner, ScannedSymbol
from core.risk_manager import DynamicRiskManager, RiskLevels


def _make_recommendation(symbol: str) -> TradeRecommendation:
    return TradeRecommendation(
        symbol=symbol,
        market_regime="TRENDING_BULL",
        trader_analysis="test",
        investor_analysis="test",
        signal="BUY",
        confidence_score=80,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
        trader_commentary="test",
    )


def _make_scanned(symbol: str) -> ScannedSymbol:
    return ScannedSymbol(
        symbol=symbol,
        regime=MarketRegime.TRENDING_BULL,
        cumulative_return_pct=15.0,
        annualized_volatility_pct=40.0,
        trend_strength_r2=0.8,
        last_close=100.0,
    )


class FakeScanner:
    def __init__(self, scanned: List[ScannedSymbol]) -> None:
        self._scanned = scanned
        self.calls: List[List[str]] = []

    def scan_and_filter(self, symbols: List[str]) -> List[ScannedSymbol]:
        self.calls.append(list(symbols))
        return self._scanned


class FakeAnalyzer:
    def __init__(self, result: Optional[Dict[str, Any]]) -> None:
        self._result = result
        self.calls: List[str] = []

    def analyze(self, symbol: str) -> Optional[Dict[str, Any]]:
        self.calls.append(symbol)
        return self._result


class FakeRiskManager:
    def calculate(self, entry_price: float, atr: float) -> RiskLevels:
        return RiskLevels(
            entry_price=entry_price, atr=atr,
            stop_loss=entry_price - 1.5 * atr,
            take_profit_1=entry_price + 2 * atr,
            take_profit_2=entry_price + 3 * atr,
            risk_per_unit=1.5 * atr,
            reward_per_unit_tp1=2 * atr,
            risk_reward_ratio=2 / 1.5,
            is_valid=True,
        )


class FakeNewsAdapter:
    def get_sentiment(self, symbol: str) -> Optional[Dict[str, Any]]:
        return None


class FakeAiPersona:
    def __init__(self) -> None:
        self.calls: List[str] = []

    def generate_recommendation(self, symbol, market_regime, analysis, risk, news_sentiment=None) -> TradeRecommendation:
        self.calls.append(symbol)
        return _make_recommendation(symbol)


def _build_engine(
    scanned: List[ScannedSymbol], analyzer_result: Optional[Dict[str, Any]]
) -> Tuple[HybridTradingEngine, FakeScanner, FakeAnalyzer, FakeAiPersona]:
    scanner = FakeScanner(scanned)
    analyzer = FakeAnalyzer(analyzer_result)
    ai_persona = FakeAiPersona()
    engine = HybridTradingEngine(
        scanner=scanner,
        analyzer=analyzer,
        risk_manager=FakeRiskManager(),
        ai_persona=ai_persona,
        news_adapter=FakeNewsAdapter(),
    )
    return engine, scanner, analyzer, ai_persona


# ─────────────────────────────────────────────────────────────────────────
# Behavior is unchanged — DI via fakes satisfying the new Protocols
# ─────────────────────────────────────────────────────────────────────────

def test_run_produces_recommendation_for_each_scanned_symbol():
    engine, scanner, analyzer, ai_persona = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0}
    )

    result = engine.run(["BTC-USD"])

    assert [r.symbol for r in result] == ["BTC-USD"]
    assert scanner.calls == [["BTC-USD"]]
    assert analyzer.calls == ["BTC-USD"]
    assert ai_persona.calls == ["BTC-USD"]


def test_run_skips_symbol_when_analyzer_returns_none():
    engine, _, _, ai_persona = _build_engine([_make_scanned("BTC-USD")], None)

    result = engine.run(["BTC-USD"])

    assert result == []
    assert ai_persona.calls == []


def test_second_call_within_ttl_uses_cache_and_skips_downstream_layers():
    engine, scanner, analyzer, ai_persona = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0}
    )

    engine.run(["BTC-USD"])
    engine.run(["BTC-USD"])

    assert scanner.calls == [["BTC-USD"], ["BTC-USD"]]  # scanner runs every call
    assert analyzer.calls == ["BTC-USD"]                 # analyzer NOT re-called (cache hit)
    assert ai_persona.calls == ["BTC-USD"]                # LLM NOT re-called (cache hit)


def test_run_continues_when_a_symbol_raises():
    class RaisingAnalyzer:
        def analyze(self, symbol: str) -> Optional[Dict[str, Any]]:
            if symbol == "BAD-USD":
                raise RuntimeError("boom")
            return {"current_price": 100.0, "atr_daily": 2.0}

    engine, _, _, ai_persona = _build_engine(
        [_make_scanned("BAD-USD"), _make_scanned("BTC-USD")], None
    )
    engine.analyzer = RaisingAnalyzer()

    result = engine.run(["BAD-USD", "BTC-USD"])

    assert [r.symbol for r in result] == ["BTC-USD"]
    assert ai_persona.calls == ["BTC-USD"]


def test_constructor_still_accepts_the_same_keyword_arguments_as_before():
    """Retyping the parameters must not change their names, order, or
    defaults - existing call sites using keyword arguments (e.g.
    core/test_engine.py, api/v1/endpoints/signals.py) must keep working
    unmodified."""
    engine = HybridTradingEngine(
        scanner=FakeScanner([]),
        analyzer=FakeAnalyzer(None),
        risk_manager=FakeRiskManager(),
        ai_persona=FakeAiPersona(),
        news_adapter=FakeNewsAdapter(),
        recommendation_cache_ttl_seconds=5.0,
    )
    assert engine._recommendation_cache._ttl_seconds == 5.0


# ─────────────────────────────────────────────────────────────────────────
# Backward compatibility — concrete production classes still satisfy the
# new Protocols (structural check via issubclass, no instantiation/network
# needed, so this doesn't require a GROQ_API_KEY or any live credentials).
# ─────────────────────────────────────────────────────────────────────────

def test_concrete_scanner_satisfies_the_protocol():
    assert issubclass(MarketRegimeScanner, RegimeScannerProtocol)


def test_concrete_analyzer_satisfies_the_protocol():
    assert issubclass(MultiTimeframeAnalyzer, TimeframeAnalyzerProtocol)


def test_concrete_risk_manager_satisfies_the_protocol():
    assert issubclass(DynamicRiskManager, RiskManagerProtocol)


def test_concrete_news_adapter_satisfies_the_protocol():
    assert issubclass(NewsSentimentAdapter, NewsSentimentProtocol)


def test_concrete_ai_persona_satisfies_the_protocol():
    assert issubclass(AITraderPersona, TraderPersonaProtocol)


def test_default_constructor_still_falls_back_to_concrete_classes_when_not_dictated():
    """HybridTradingEngine()'s no-argument defaults (`scanner or
    MarketRegimeScanner()`, etc.) are untouched by this task - only their
    type hints changed. Constructing the cheap collaborators (no network
    I/O in their own __init__) with zero arguments must still work exactly
    as before. AITraderPersona is deliberately excluded here since its
    constructor builds a real Groq client that may require GROQ_API_KEY -
    unrelated to this refactor, and already covered structurally by the
    issubclass check above."""
    engine = HybridTradingEngine(ai_persona=FakeAiPersona())
    assert isinstance(engine.scanner, MarketRegimeScanner)
    assert isinstance(engine.analyzer, MultiTimeframeAnalyzer)
    assert isinstance(engine.risk_manager, DynamicRiskManager)
    assert isinstance(engine.news_adapter, NewsSentimentAdapter)
