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

The `profile="investor"` / `check_alerts()` sections below (ported from a
diverged branch, see InvestorPersona/MarketAnomalyDetector) follow the
same fakes-over-mocks convention as the rest of this file.
"""
from typing import Any, Dict, List, Optional, Tuple

from core.ai_trader_persona import AITraderPersona, TradeRecommendation
from core.hybrid_engine import HybridTradingEngine
from core.interfaces import (
    AnomalyDetectorProtocol,
    InvestorPersonaProtocol,
    NewsSentimentProtocol,
    RegimeScannerProtocol,
    RiskManagerProtocol,
    TimeframeAnalyzerProtocol,
    TraderPersonaProtocol,
)
from core.investor_persona import HorizonView, InvestorPersona, InvestorRecommendation
from core.market_anomaly_detector import MarketAlert, MarketAnomalyDetector
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


def _make_investor_recommendation(symbol: str) -> InvestorRecommendation:
    horizon = HorizonView(signal="BUY", confidence_score=60, rationale="test")
    return InvestorRecommendation(
        symbol=symbol,
        market_regime="TRENDING_BULL",
        horizon_1_week=horizon,
        horizon_1_month=horizon,
        horizon_1_year=horizon,
        investor_commentary="test",
    )


class FakeScanner:
    def __init__(self, scanned: List[ScannedSymbol]) -> None:
        self._scanned = scanned
        self.calls: List[List[str]] = []
        self.scan_calls: List[List[str]] = []

    def scan_and_filter(self, symbols: List[str]) -> List[ScannedSymbol]:
        self.calls.append(list(symbols))
        return self._scanned

    def scan(self, symbols: List[str]) -> List[ScannedSymbol]:
        self.scan_calls.append(list(symbols))
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


class FakeInvestorPersona:
    def __init__(self) -> None:
        self.calls: List[str] = []

    def generate_recommendation(self, symbol, market_regime, analysis, news_sentiment=None) -> InvestorRecommendation:
        self.calls.append(symbol)
        return _make_investor_recommendation(symbol)


class FakeAnomalyDetector:
    def __init__(self, alert: Optional[MarketAlert] = None) -> None:
        self._alert = alert
        self.calls: List[str] = []

    def detect(self, symbol, regime, analysis, news_sentiment) -> Optional[MarketAlert]:
        self.calls.append(symbol)
        return self._alert


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
        investor_persona=FakeInvestorPersona(),
        news_adapter=FakeNewsAdapter(),
        anomaly_detector=FakeAnomalyDetector(),
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


# ─────────────────────────────────────────────────────────────────────────
# profile="investor" — separate persona, separate cache, no risk manager
# ─────────────────────────────────────────────────────────────────────────

def test_default_profile_is_trader():
    engine, _, _, ai_persona = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0}
    )

    result = engine.run(["AAPL"])

    assert isinstance(result[0], TradeRecommendation)
    assert ai_persona.calls == ["AAPL"]
    assert engine.investor_persona.calls == []


def test_investor_profile_uses_investor_persona_and_skips_risk_manager():
    engine, _, _, ai_persona = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0}
    )

    result = engine.run(["AAPL"], profile="investor")

    assert isinstance(result[0], InvestorRecommendation)
    assert engine.investor_persona.calls == ["AAPL"]
    assert ai_persona.calls == []


def test_investor_cache_is_independent_from_trader_cache():
    engine, _, analyzer, ai_persona = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0}
    )

    trader_result = engine.run(["AAPL"], profile="trader")
    investor_result = engine.run(["AAPL"], profile="investor")

    assert isinstance(trader_result[0], TradeRecommendation)
    assert isinstance(investor_result[0], InvestorRecommendation)
    assert analyzer.calls == ["AAPL", "AAPL"]  # each profile missed its own cache once
    assert ai_persona.calls == ["AAPL"]
    assert engine.investor_persona.calls == ["AAPL"]


# ─────────────────────────────────────────────────────────────────────────
# check_alerts() — unfiltered scan, its own 2-minute cache, reuses run()'s
# already-fetched analysis/news data as a side effect.
# ─────────────────────────────────────────────────────────────────────────

def test_check_alerts_uses_the_unfiltered_scan_not_scan_and_filter():
    engine, scanner, _, _ = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0}
    )

    engine.check_alerts(["AAPL"])

    assert scanner.scan_calls == [["AAPL"]]
    assert scanner.calls == []


def test_check_alerts_returns_an_alert_when_the_detector_triggers():
    alert = MarketAlert(
        symbol="AAPL", alert_type="PRICE_VOLUME_SHOCK", severity="MEDIUM",
        direction="BULLISH", message="test",
    )
    engine, _, _, _ = _build_engine([_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0})
    engine.anomaly_detector = FakeAnomalyDetector(alert)

    result = engine.check_alerts(["AAPL"])

    assert result == [alert]


def test_check_alerts_handles_missing_analysis_without_raising():
    engine, _, _, _ = _build_engine([_make_scanned("AAPL")], None)

    result = engine.check_alerts(["AAPL"])

    assert result == []


def test_check_alerts_no_alert_is_cached_and_analyzer_not_rechecked():
    engine, _, analyzer, _ = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0}
    )

    engine.check_alerts(["AAPL"])
    engine.check_alerts(["AAPL"])

    assert analyzer.calls == ["AAPL"]


def test_run_populates_the_alert_cache_so_check_alerts_reuses_it():
    alert = MarketAlert(
        symbol="AAPL", alert_type="NEWS_SHOCK", severity="MEDIUM",
        direction="BEARISH", message="test",
    )
    engine, _, analyzer, _ = _build_engine([_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0})
    engine.anomaly_detector = FakeAnomalyDetector(alert)

    engine.run(["AAPL"])
    result = engine.check_alerts(["AAPL"])

    assert result == [alert]
    assert analyzer.calls == ["AAPL"]  # run()'da çekilen veri check_alerts() tarafından yeniden kullanıldı


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
        investor_persona=FakeInvestorPersona(),
        news_adapter=FakeNewsAdapter(),
        anomaly_detector=FakeAnomalyDetector(),
        recommendation_cache_ttl_seconds=5.0,
        alert_cache_ttl_seconds=1.0,
    )
    assert engine._recommendation_cache._ttl_seconds == 5.0
    assert engine._investor_cache._ttl_seconds == 5.0
    assert engine._alert_cache._ttl_seconds == 1.0


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


def test_concrete_investor_persona_satisfies_the_protocol():
    assert issubclass(InvestorPersona, InvestorPersonaProtocol)


def test_concrete_anomaly_detector_satisfies_the_protocol():
    assert issubclass(MarketAnomalyDetector, AnomalyDetectorProtocol)


def test_default_constructor_still_falls_back_to_concrete_classes_when_not_dictated():
    """HybridTradingEngine()'s no-argument defaults (`scanner or
    MarketRegimeScanner()`, etc.) are untouched by this task - only their
    type hints changed. Constructing the cheap collaborators (no network
    I/O in their own __init__) with zero arguments must still work exactly
    as before. AITraderPersona and InvestorPersona are deliberately
    excluded here since their constructors build a real Groq client that
    may require GROQ_API_KEY - unrelated to this refactor, and already
    covered structurally by the issubclass checks above."""
    engine = HybridTradingEngine(ai_persona=FakeAiPersona(), investor_persona=FakeInvestorPersona())
    assert isinstance(engine.scanner, MarketRegimeScanner)
    assert isinstance(engine.analyzer, MultiTimeframeAnalyzer)
    assert isinstance(engine.risk_manager, DynamicRiskManager)
    assert isinstance(engine.news_adapter, NewsSentimentAdapter)
    assert isinstance(engine.anomaly_detector, MarketAnomalyDetector)
