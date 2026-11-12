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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import api.v1.endpoints.signals as signals_endpoint
import core.hybrid_engine as core_hybrid_engine
from core.ai_trader_persona import AITraderPersona, TradeRecommendation, TradeSignal
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
from core.no_trade import NoTradeOutcome, NoTradeReason
from core.regime_scanner import MarketRegime, MarketRegimeScanner, ScannedSymbol
from core.risk_manager import DynamicRiskManager, RiskLevels
from decision_engine.exceptions import NoValidVotesError
from decision_engine.models import DecisionOutput, Prediction


def _make_recommendation(symbol: str) -> TradeRecommendation:
    """What `AITraderPersona.generate_recommendation` actually returns
    (Finding F8 fix): narrative only - `signal`/`confidence_score`/
    `entry_price`/`stop_loss`/`take_profit_*`/`signal_source` are never
    set by the LLM, so this fake leaves them at their `None` default,
    exactly like the real, scrubbed object would."""
    return TradeRecommendation(
        symbol=symbol,
        market_regime="TRENDING_BULL",
        trader_analysis="test",
        investor_analysis="test",
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
    """What `InvestorPersona.generate_recommendation` actually returns
    (Finding F9 fix): `rationale`-only per horizon - `signal`/
    `confidence_score` are never set by the LLM for ANY horizon (not
    even 1-week), so this fake leaves them at their `None` default."""
    horizon = HorizonView(rationale="test")
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


def _make_decision_output(
    symbol: str, decision: Prediction = Prediction.BUY, confidence: float = 0.6,
    data_sufficiency: float = 1.0,
) -> DecisionOutput:
    return DecisionOutput(
        symbol=symbol, decision=decision, confidence=confidence,
        expected_return=0.01, expected_volatility=0.02,
        aggregation_strategy_version="test", data_sufficiency=data_sufficiency,
        evidence=[], engine_results=[],
    )


class FakeDecisionEngine:
    """Default decision (BUY, confidence=0.6) deliberately differs from
    `_make_recommendation`'s hardcoded `confidence_score=80` (which maps
    to 60 after `_apply_canonical_decision` overrides it) - so any test
    that happened to assert the LLM's own confidence_score would fail
    loudly instead of silently passing by coincidence."""

    def __init__(self, decision_output: Optional[DecisionOutput] = None, raises: Optional[Exception] = None) -> None:
        self._decision_output = decision_output
        self._raises = raises
        self.calls: List[str] = []

    def decide(self, symbol: str, strict: bool = False) -> DecisionOutput:
        self.calls.append(symbol)
        if self._raises is not None:
            raise self._raises
        return self._decision_output or _make_decision_output(symbol)


def _build_engine(
    scanned: List[ScannedSymbol], analyzer_result: Optional[Dict[str, Any]],
    decision_engine: Optional[Any] = None,
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
        decision_engine=decision_engine or FakeDecisionEngine(),
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


def test_no_trade_outcome_is_never_cached_for_the_15_minute_ttl():
    """CTO Remediation Plan Revision 4 Section 5.2: a transient Decision
    Engine failure must not leave a stale NO_TRADE result served for the
    recommendation cache's full 15-minute TTL. `_process_symbol` returns
    before either `cache.set()` call for a NO_TRADE outcome - proven
    here by a second, successful run (decision engine fixed in between)
    immediately producing a real recommendation, not a cached NO_TRADE
    the first call would otherwise have poisoned the cache with."""
    decision_engine = FakeDecisionEngine(raises=RuntimeError("transient failure"))
    engine, _, analyzer, ai_persona = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    first = engine.run(["BTC-USD"])
    assert first == []

    decision_engine._raises = None  # the transient failure has since cleared
    second = engine.run(["BTC-USD"])

    assert len(second) == 1
    # Both the analyzer and the LLM were called again on the second run
    # - a cache hit would have skipped them, proving nothing was cached
    # from the first (NO_TRADE) call.
    assert analyzer.calls == ["BTC-USD", "BTC-USD"]
    assert ai_persona.calls == ["BTC-USD", "BTC-USD"]


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
# Decision Engine is the ONLY decision authority (CTO Remediation Plan
# Revision 4, Finding F8/F9). The LLM can never supply, override, or
# survive-as-a-fallback a final signal/confidence/trade-level - a
# Decision Engine failure now produces an explicit NO_TRADE outcome
# (the symbol is dropped), never the LLM's own unvalidated signal.
# ─────────────────────────────────────────────────────────────────────────

def test_trader_recommendation_signal_is_overridden_by_the_decision_engine():
    decision_engine = FakeDecisionEngine(_make_decision_output("BTC-USD", Prediction.SELL, confidence=0.9))
    engine, _, _, ai_persona = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["BTC-USD"])

    # The LLM (FakeAiPersona/_make_recommendation) never supplies a
    # signal at all (Finding F8) - the Decision Engine's SELL/0.9 is the
    # only source of the final signal.
    assert ai_persona.calls == ["BTC-USD"]  # LLM was still called (for the narrative fields)
    assert decision_engine.calls == ["BTC-USD"]
    assert result[0].signal == TradeSignal.STRONG_SELL  # 0.9 confidence crosses the "strong" bar
    assert result[0].confidence_score == 90
    assert result[0].signal_source == "decision_engine"
    # entry_price is risk_manager-sourced (direction-agnostic - just the
    # current price), unaffected by direction.
    assert result[0].entry_price == 100.0
    # Finding 8's risk-geometry issue: DynamicRiskManager only ever
    # computes long-side stop/take-profit levels - a SELL/STRONG_SELL
    # decision must never receive them as if they were its own.
    assert result[0].stop_loss is None
    assert result[0].take_profit_1 is None
    assert result[0].take_profit_2 is None


def test_trader_recommendation_buy_signal_keeps_the_long_side_risk_levels():
    """The mirror image of the SELL test above: BUY/STRONG_BUY is
    exactly the direction DynamicRiskManager's formulas are valid for,
    so the real levels are attached, not omitted."""
    decision_engine = FakeDecisionEngine(_make_decision_output("BTC-USD", Prediction.BUY, confidence=0.5))
    engine, _, _, _ = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["BTC-USD"])

    assert result[0].signal == TradeSignal.BUY
    assert result[0].stop_loss == 97.0  # FakeRiskManager: entry(100) - 1.5*atr(2)
    assert result[0].take_profit_1 == 104.0  # entry + 2*atr
    assert result[0].take_profit_2 == 106.0  # entry + 3*atr


def test_a_genuine_canonical_hold_remains_hold():
    """A real HOLD vote from the Decision Engine is a real decision, not
    NO_TRADE - it must survive unchanged, with no invented risk levels
    (there is no position to manage)."""
    decision_engine = FakeDecisionEngine(_make_decision_output("BTC-USD", Prediction.HOLD, confidence=0.5))
    engine, _, _, _ = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["BTC-USD"])

    assert len(result) == 1
    assert result[0].signal == TradeSignal.NEUTRAL
    assert result[0].signal_source == "decision_engine"
    assert result[0].stop_loss is None


def test_trader_recommendation_becomes_no_trade_when_decision_engine_raises():
    """Finding F8 fix: a Decision Engine exception no longer falls back
    to the LLM's own (unvalidated) signal - the symbol is dropped from
    the result entirely, never returned with a fabricated signal."""
    decision_engine = FakeDecisionEngine(raises=RuntimeError("feature store unavailable"))
    engine, _, _, ai_persona = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["BTC-USD"])

    assert result == []  # NOT [_make_recommendation("BTC-USD")] - no fake signal survives
    assert ai_persona.calls == ["BTC-USD"]  # the LLM was still called; its output was discarded


def test_trader_recommendation_becomes_no_trade_when_there_are_zero_valid_votes():
    decision_engine = FakeDecisionEngine(raises=NoValidVotesError("BTC-USD"))
    engine, _, _, _ = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["BTC-USD"])

    assert result == []


def test_trader_recommendation_becomes_no_trade_when_data_sufficiency_is_too_low():
    """Finding 3: decide(strict=True) can return normally with very few
    engines voting - that low-confidence-input output must be treated
    the same as the exception path (NO_TRADE), not silently produce a
    recommendation anyway."""
    decision_engine = FakeDecisionEngine(
        _make_decision_output("BTC-USD", Prediction.SELL, confidence=0.9, data_sufficiency=0.2)
    )
    engine, _, _, _ = _build_engine(
        [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["BTC-USD"])

    assert result == []


class TestNoTradeReasonMapping:
    """The three NO_TRADE reason codes (CTO Remediation Plan Revision 4
    Section 5.1) map to distinct, specific failure modes - verified
    directly against `_apply_canonical_decision`'s return value, since
    `run()` only exposes "the symbol was dropped," not why."""

    def test_decision_engine_exception_maps_to_decision_engine_unavailable(self):
        engine, _, _, _ = _build_engine(
            [], None, decision_engine=FakeDecisionEngine(raises=RuntimeError("boom"))
        )
        narrative = _make_recommendation("BTC-USD")
        risk = FakeRiskManager().calculate(entry_price=100.0, atr=2.0)

        outcome = engine._apply_canonical_decision("BTC-USD", narrative, risk)

        assert isinstance(outcome, NoTradeOutcome)
        assert outcome.reason == NoTradeReason.DECISION_ENGINE_UNAVAILABLE
        assert outcome.symbol == "BTC-USD"

    def test_zero_valid_votes_maps_to_no_valid_engine_votes(self):
        engine, _, _, _ = _build_engine(
            [], None, decision_engine=FakeDecisionEngine(raises=NoValidVotesError("BTC-USD"))
        )
        narrative = _make_recommendation("BTC-USD")
        risk = FakeRiskManager().calculate(entry_price=100.0, atr=2.0)

        outcome = engine._apply_canonical_decision("BTC-USD", narrative, risk)

        assert isinstance(outcome, NoTradeOutcome)
        assert outcome.reason == NoTradeReason.NO_VALID_ENGINE_VOTES

    def test_insufficient_data_sufficiency_maps_to_insufficient_data(self):
        decision_engine = FakeDecisionEngine(
            _make_decision_output("BTC-USD", Prediction.SELL, confidence=0.9, data_sufficiency=0.2)
        )
        engine, _, _, _ = _build_engine([], None, decision_engine=decision_engine)
        narrative = _make_recommendation("BTC-USD")
        risk = FakeRiskManager().calculate(entry_price=100.0, atr=2.0)

        outcome = engine._apply_canonical_decision("BTC-USD", narrative, risk)

        assert isinstance(outcome, NoTradeOutcome)
        assert outcome.reason == NoTradeReason.INSUFFICIENT_DATA

    def test_no_trade_outcome_carries_no_trade_parameters(self):
        """NoTradeOutcome has no signal/confidence_score/entry_price/
        stop_loss/take_profit_* field at all - not just set to None."""
        NoTradeOutcome(symbol="BTC-USD", reason=NoTradeReason.INSUFFICIENT_DATA)

        assert set(NoTradeOutcome.model_fields) == {"symbol", "reason", "attempted_at"}


class TestNoTradeExecutionSafety:
    """CTO review (Task 0.1.2): proves NO_TRADE cannot trigger position
    sizing, order creation, or paper-trading execution - not merely
    that a NoTradeOutcome object has the right shape (that is already
    covered above).

    Architectural finding, stated explicitly per the task's own
    instruction to explain rather than invent abstractions: there is no
    existing call path from `core.hybrid_engine`/`api.v1.endpoints.
    signals` to `paper_trading` at all today. `paper_trading.orders.
    OrderService.create_order` takes manual, caller-supplied
    `account_id`/`side`/`quantity` parameters - no recommendation/
    decision object of any kind - and nothing in this engine's module
    imports `paper_trading`. There is therefore no production
    sizing/order-creation *method* to spy on and prove "never called",
    because none is ever called by this path, for ANY outcome (BUY,
    SELL, HOLD, or NO_TRADE alike) - the coupling this task asks to
    rule out does not exist to begin with.

    Given that, this class proves the strongest two things the actual
    architecture supports, without inventing a new abstraction or
    wiring a connection that doesn't exist purely to have something to
    test:
    1. A behavioral spy on the one real mechanism through which a
       recommendation could ever reach ANY second caller (today's UI,
       or any future consumer built on top of it) - the recommendation
       cache's own `.set()` method - proving a NO_TRADE outcome is
       never written there.
    2. A structural, regression-proof guarantee (mirroring
       `tests/test_research_isolation.py`'s own AST-scan convention)
       that the modules producing/returning `NoTradeOutcome` have zero
       import dependency on `paper_trading`, now or after any future
       change - not merely "doesn't call it today by observation."
    """

    def test_no_trade_outcome_is_never_written_to_the_recommendation_cache(self):
        """The recommendation cache is the real execution boundary this
        architecture has: `_process_symbol` returns a value either by
        writing it to this cache and returning it, or (for NO_TRADE) by
        returning `None` without writing. A spy on the cache's own
        `.set()` - the actual production method, not a re-implementation
        of it - proves the second branch is the one actually taken."""
        decision_engine = FakeDecisionEngine(raises=RuntimeError("boom"))
        engine, _, _, ai_persona = _build_engine(
            [_make_scanned("BTC-USD")], {"current_price": 100.0, "atr_daily": 2.0},
            decision_engine=decision_engine,
        )
        cache_set_calls: List[Any] = []
        original_set = engine._recommendation_cache.set

        def spy_set(key: str, value: Any) -> None:
            cache_set_calls.append((key, value))
            original_set(key, value)

        engine._recommendation_cache.set = spy_set  # type: ignore[method-assign]

        result = engine.run(["BTC-USD"])

        assert result == []
        assert cache_set_calls == []  # the spy proves .set() was never invoked at all
        assert ai_persona.calls == ["BTC-USD"]  # confirms the run actually executed, not skipped

    def test_no_trade_outcome_is_never_written_to_the_investor_cache(self):
        decision_engine = FakeDecisionEngine(raises=RuntimeError("boom"))
        engine, _, _, _ = _build_engine(
            [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0},
            decision_engine=decision_engine,
        )
        cache_set_calls: List[Any] = []
        original_set = engine._investor_cache.set

        def spy_set(key: str, value: Any) -> None:
            cache_set_calls.append((key, value))
            original_set(key, value)

        engine._investor_cache.set = spy_set  # type: ignore[method-assign]

        result = engine.run(["AAPL"], profile="investor")

        assert result == []
        assert cache_set_calls == []

    def test_hybrid_engine_module_has_no_import_path_to_paper_trading(self):
        """Structural safety guarantee: the module that produces
        `NoTradeOutcome` must have zero import dependency on
        `paper_trading` - a real AST scan of the actual source file, not
        a string search of history, so a future accidental import is
        caught immediately rather than relying on this never changing
        unnoticed."""
        import ast

        source = Path(core_hybrid_engine.__file__).read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden = {name for name in imported if name.split(".")[0] == "paper_trading"}
        assert forbidden == set()

    def test_signals_endpoint_module_has_no_import_path_to_paper_trading(self):
        """Same guarantee for the API layer that exposes this engine -
        `POST /api/v1/signals/analyze` itself must never gain a direct
        paper_trading dependency either."""
        import ast

        source = Path(signals_endpoint.__file__).read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden = {name for name in imported if name.split(".")[0] == "paper_trading"}
        assert forbidden == set()


def test_investor_profile_1_week_horizon_is_overridden_by_the_decision_engine():
    """profile="investor" produces three per-horizon views, but (Finding
    F9) only horizon_1_week is ever backed by the Decision Engine - the
    closest existing match to a current-conditions vote.
    horizon_1_month/horizon_1_year stay null/unavailable always: no
    validated horizon-specific model exists for them, and the LLM never
    supplies a signal/confidence for any horizon (see
    _make_investor_recommendation)."""
    decision_engine = FakeDecisionEngine(_make_decision_output("AAPL", Prediction.SELL, confidence=0.9))
    engine, _, _, _ = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["AAPL"], profile="investor")

    assert decision_engine.calls == ["AAPL"]
    rec = result[0]
    assert rec.horizon_1_week.signal == TradeSignal.STRONG_SELL
    assert rec.horizon_1_week.confidence_score == 90
    assert rec.horizon_1_week.signal_source == "decision_engine"
    # horizon_1_month/horizon_1_year remain null - never a validated
    # decision, never an LLM-authored one either (Finding F9).
    assert rec.horizon_1_month.signal is None
    assert rec.horizon_1_month.confidence_score is None
    assert rec.horizon_1_year.signal is None
    assert rec.horizon_1_year.confidence_score is None


def test_investor_recommendation_becomes_no_trade_when_decision_engine_fails():
    """Finding F8/F9 fix: a Decision Engine failure for the investor
    profile no longer falls back to any LLM-authored horizon_1_week
    signal (there isn't one to fall back to - it was never set) - the
    entire recommendation becomes NO_TRADE and the symbol is dropped,
    exactly like the trader profile."""
    decision_engine = FakeDecisionEngine(raises=RuntimeError("feature store unavailable"))
    engine, _, _, _ = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["AAPL"], profile="investor")

    assert result == []


def test_investor_recommendation_becomes_no_trade_when_data_sufficiency_is_too_low():
    decision_engine = FakeDecisionEngine(
        _make_decision_output("AAPL", Prediction.SELL, confidence=0.9, data_sufficiency=0.2)
    )
    engine, _, _, _ = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["AAPL"], profile="investor")

    assert result == []


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
