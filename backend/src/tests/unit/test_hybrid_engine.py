"""
Unit tests for core/hybrid_engine.py orchestration logic. All layers
(scanner, analyzer, risk_manager, ai_persona, investor_persona,
news_adapter, anomaly_detector) are injected as mocks — no network calls,
no LLM calls. Verifies profile branching, cache behavior (both the
recommendation caches and the alert cache), and error handling.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from unittest.mock import MagicMock

from core.ai_trader_persona import TradeRecommendation, TradeSignal
from core.hybrid_engine import HybridTradingEngine
from core.investor_persona import HorizonView, InvestorRecommendation
from core.market_anomaly_detector import MarketAlert
from core.no_trade import NoTradeOutcome, NoTradeReason
from core.regime_scanner import MarketRegime, ScannedSymbol
from core.risk_manager import RiskLevels
from decision_engine.exceptions import NoValidVotesError
from decision_engine.models import DecisionOutput, Prediction


def _scanned(symbol="AAPL", regime=MarketRegime.TRENDING_BULL):
    return ScannedSymbol(
        symbol=symbol, regime=regime, cumulative_return_pct=10.0,
        annualized_volatility_pct=20.0, trend_strength_r2=0.8, last_close=180.0,
    )


def _analysis():
    return {
        "symbol": "AAPL", "current_price": 180.0, "atr_daily": 2.5,
        "macro": {"trend_direction": "BULLISH", "daily_return_pct": 1.0, "price_move_atr_multiple": 0.4},
        "micro": {"volume_ratio": 1.2, "rsi_14": 55.0},
        "patterns": {},
    }


def _trade_rec(symbol="AAPL"):
    """What `AITraderPersona.generate_recommendation` actually returns
    (Finding F8): narrative only, decision fields left at their `None`
    default - `core.hybrid_engine._apply_canonical_decision` is the only
    thing that ever sets them."""
    return TradeRecommendation(
        symbol=symbol, market_regime="TRENDING_BULL",
        trader_analysis="a", investor_analysis="b",
        trader_commentary="c",
    )


def _investor_rec(symbol="AAPL"):
    """What `InvestorPersona.generate_recommendation` actually returns
    (Finding F9): `rationale`-only per horizon - signal/confidence_score
    are never set by the LLM for any horizon, not even 1-week."""
    horizon = HorizonView(rationale="r")
    return InvestorRecommendation(
        symbol=symbol, market_regime="TRENDING_BULL",
        horizon_1_week=horizon, horizon_1_month=horizon, horizon_1_year=horizon,
        investor_commentary="genel",
    )


def _risk():
    return RiskLevels(
        entry_price=180.0, atr=2.5, stop_loss=176.25, take_profit_1=185.0,
        take_profit_2=187.5, risk_per_unit=3.75, reward_per_unit_tp1=5.0,
        risk_reward_ratio=1.33, is_valid=False,
    )


def _decision_output(symbol="AAPL", decision=Prediction.BUY, confidence=0.70, data_sufficiency=1.0):
    """Default (BUY, 0.70) is deliberately chosen to map onto the exact
    same (TradeSignal.BUY, confidence_score=70) `_trade_rec()` already
    hardcodes - so `_apply_canonical_decision`'s override is a no-op for
    every pre-existing exact-equality assertion (`result == [_trade_rec()]`)
    below, and only the dedicated Decision Engine tests further down
    need a differing value to prove the override actually happens."""
    return DecisionOutput(
        symbol=symbol, decision=decision, confidence=confidence,
        expected_return=0.01, expected_volatility=0.02,
        aggregation_strategy_version="test", data_sufficiency=data_sufficiency,
        evidence=[], engine_results=[],
    )


def _make_decision_engine(**decide_kwargs) -> MagicMock:
    mock = MagicMock()
    mock.decide.return_value = _decision_output(**decide_kwargs)
    return mock


def _make_engine(**overrides) -> HybridTradingEngine:
    defaults = dict(
        scanner=MagicMock(),
        analyzer=MagicMock(),
        risk_manager=MagicMock(),
        ai_persona=MagicMock(),
        investor_persona=MagicMock(),
        news_adapter=MagicMock(),
        anomaly_detector=MagicMock(),
        decision_engine=_make_decision_engine(),
    )
    defaults.update(overrides)
    return HybridTradingEngine(**defaults)


class TestRunTraderProfile:
    def test_default_profile_is_trader(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        # Finding F8: the final signal/confidence/risk-levels come
        # entirely from the Decision Engine/risk_manager, never from
        # _trade_rec()'s narrative-only fields (which stay None) - so a
        # plain-equality check against _trade_rec() would fail; assert
        # the orchestrated fields explicitly instead.
        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert result[0].signal == TradeSignal.BUY  # default _make_decision_engine(): BUY/0.70
        assert result[0].confidence_score == 70
        assert result[0].signal_source == "decision_engine"
        engine.ai_persona.generate_recommendation.assert_called_once()
        engine.investor_persona.generate_recommendation.assert_not_called()

    def test_trader_profile_calls_risk_manager(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        engine.run(["AAPL"], profile="trader")

        engine.risk_manager.calculate.assert_called_once_with(entry_price=180.0, atr=2.5)


class TestRunInvestorProfile:
    def test_investor_profile_uses_investor_persona_and_skips_risk_manager(self):
        # confidence=0.60 chosen only so STRONG_BUY's 0.75 threshold
        # isn't crossed (keeps this test's assertion simple); the
        # dedicated TestCanonicalDecisionOverride tests below prove the
        # override itself in detail. _investor_rec()'s own
        # horizon_1_week carries no signal/confidence (Finding F9) - the
        # Decision Engine is the only source of either.
        engine = _make_engine(decision_engine=_make_decision_engine(confidence=0.60))
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"], profile="investor")

        assert len(result) == 1
        assert result[0].horizon_1_week.signal == TradeSignal.BUY
        assert result[0].horizon_1_week.confidence_score == 60
        assert result[0].horizon_1_month.signal is None
        assert result[0].horizon_1_year.signal is None
        engine.investor_persona.generate_recommendation.assert_called_once()
        engine.ai_persona.generate_recommendation.assert_not_called()
        engine.risk_manager.calculate.assert_not_called()

    def test_investor_cache_independent_from_trader_cache(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        trader_result = engine.run(["AAPL"], profile="trader")
        investor_result = engine.run(["AAPL"], profile="investor")

        assert isinstance(trader_result[0], TradeRecommendation)
        assert isinstance(investor_result[0], InvestorRecommendation)
        assert engine.analyzer.analyze.call_count == 2  # her profil kendi cache'inde miss oldu


class TestProcessSymbolErrorHandling:
    def test_returns_empty_list_when_analysis_is_none(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = None

        result = engine.run(["AAPL"])

        assert result == []

    def test_exception_in_persona_does_not_crash_run(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.side_effect = RuntimeError("boom")
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        assert result == []


class TestRecommendationCache:
    def test_cache_hit_skips_analyzer(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        engine.run(["AAPL"])
        engine.run(["AAPL"])

        assert engine.analyzer.analyze.call_count == 1


class TestCheckAlerts:
    def test_uses_unfiltered_scan(self):
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.anomaly_detector.detect.return_value = None

        engine.check_alerts(["AAPL"])

        engine.scanner.scan.assert_called_once_with(["AAPL"])
        engine.scanner.scan_and_filter.assert_not_called()

    def test_returns_alert_when_detector_triggers(self):
        alert = MarketAlert(
            symbol="AAPL", alert_type="PRICE_VOLUME_SHOCK", severity="MEDIUM",
            direction="BULLISH", message="test",
        )
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.anomaly_detector.detect.return_value = alert

        result = engine.check_alerts(["AAPL"])

        assert result == [alert]

    def test_no_alert_is_cached_and_not_rechecked(self):
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.anomaly_detector.detect.return_value = None

        engine.check_alerts(["AAPL"])
        engine.check_alerts(["AAPL"])

        assert engine.analyzer.analyze.call_count == 1

    def test_alert_cache_populated_as_side_effect_of_run(self):
        alert = MarketAlert(
            symbol="AAPL", alert_type="NEWS_SHOCK", severity="MEDIUM",
            direction="BEARISH", message="test",
        )
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = alert

        engine.run(["AAPL"])
        result = engine.check_alerts(["AAPL"])

        assert result == [alert]


class TestNoTradeReasonMapping:
    """Direct, mock-based verification that the three NO_TRADE reason
    codes map to distinct failure modes (CTO Remediation Plan Revision
    4 Section 5.1) - `_apply_canonical_decision` returns a typed
    `NoTradeOutcome`, not a dict or a bare string."""

    def test_decision_engine_exception_maps_to_decision_engine_unavailable(self):
        engine = _make_engine()
        engine.decision_engine.decide.side_effect = RuntimeError("boom")

        outcome = engine._apply_canonical_decision("AAPL", _trade_rec(), _risk())

        assert isinstance(outcome, NoTradeOutcome)
        assert outcome.reason == NoTradeReason.DECISION_ENGINE_UNAVAILABLE

    def test_zero_valid_votes_maps_to_no_valid_engine_votes(self):
        engine = _make_engine()
        engine.decision_engine.decide.side_effect = NoValidVotesError("AAPL")

        outcome = engine._apply_canonical_decision("AAPL", _trade_rec(), _risk())

        assert isinstance(outcome, NoTradeOutcome)
        assert outcome.reason == NoTradeReason.NO_VALID_ENGINE_VOTES

    def test_insufficient_data_maps_to_insufficient_data(self):
        engine = _make_engine(
            decision_engine=_make_decision_engine(decision=Prediction.SELL, confidence=0.9, data_sufficiency=0.2)
        )

        outcome = engine._apply_canonical_decision("AAPL", _trade_rec(), _risk())

        assert isinstance(outcome, NoTradeOutcome)
        assert outcome.reason == NoTradeReason.INSUFFICIENT_DATA


class TestCanonicalDecisionOverride:
    """CTO Remediation Plan Revision 4, Finding F8/F9: the Decision
    Engine is the ONLY decision authority for profile="trader" - the
    LLM never supplies, overrides, or survives-as-a-fallback a final
    signal/confidence/trade-level. A Decision Engine exception, zero
    valid votes, or insufficient data now produces an explicit NO_TRADE
    outcome (the symbol is dropped), never the LLM's own signal."""

    def test_decision_engine_output_overrides_the_llm_signal(self):
        engine = _make_engine(decision_engine=_make_decision_engine(decision=Prediction.SELL, confidence=0.9))
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        engine.decision_engine.decide.assert_called_once_with("AAPL", strict=True)
        assert result[0].signal == TradeSignal.STRONG_SELL  # 0.9 crosses the "strong" bar
        assert result[0].confidence_score == 90
        assert result[0].signal_source == "decision_engine"
        assert result[0].entry_price == 180.0  # risk_manager-sourced, direction-agnostic
        # Finding 8's risk-geometry issue: DynamicRiskManager only
        # computes long-side levels - SELL/STRONG_SELL must not get them.
        assert result[0].stop_loss is None
        assert result[0].take_profit_1 is None
        assert result[0].take_profit_2 is None

    def test_decision_engine_buy_signal_keeps_the_long_side_risk_levels(self):
        engine = _make_engine(decision_engine=_make_decision_engine(decision=Prediction.BUY, confidence=0.5))
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        assert result[0].signal == TradeSignal.BUY
        assert result[0].stop_loss == _risk().stop_loss
        assert result[0].take_profit_1 == _risk().take_profit_1

    def test_a_genuine_canonical_hold_remains_hold(self):
        engine = _make_engine(decision_engine=_make_decision_engine(decision=Prediction.HOLD, confidence=0.5))
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        assert len(result) == 1
        assert result[0].signal == TradeSignal.NEUTRAL
        assert result[0].signal_source == "decision_engine"

    def test_decision_engine_exception_produces_no_trade_not_the_llm_signal(self):
        engine = _make_engine()
        engine.decision_engine.decide.side_effect = RuntimeError("boom")
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        assert result == []  # dropped, NOT [_trade_rec()] - no fabricated signal survives

    def test_zero_valid_votes_produces_no_trade(self):
        engine = _make_engine()
        engine.decision_engine.decide.side_effect = NoValidVotesError("AAPL")
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        assert result == []

    def test_investor_profile_1_week_horizon_is_overridden_by_the_decision_engine(self):
        """decision_engine has no per-horizon concept, so only
        horizon_1_week (closest match to a current-conditions vote) is
        ever populated; horizon_1_month/horizon_1_year stay null always
        (Finding F9) - the LLM (investor_persona) never supplies a
        signal/confidence for any horizon in the first place."""
        engine = _make_engine(decision_engine=_make_decision_engine(decision=Prediction.SELL, confidence=0.9))
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"], profile="investor")

        engine.decision_engine.decide.assert_called_once_with("AAPL", strict=True)
        rec = result[0]
        assert rec.horizon_1_week.signal == TradeSignal.STRONG_SELL  # 0.9 crosses the "strong" bar
        assert rec.horizon_1_week.confidence_score == 90
        assert rec.horizon_1_week.signal_source == "decision_engine"
        assert rec.horizon_1_month.signal is None
        assert rec.horizon_1_month.confidence_score is None
        assert rec.horizon_1_year.signal is None
        assert rec.horizon_1_year.confidence_score is None
        assert engine.analyzer.analyze.call_count == 1  # run() sırasında çekilen veri yeniden kullanıldı

    def test_investor_profile_decision_engine_exception_produces_no_trade(self):
        engine = _make_engine()
        engine.decision_engine.decide.side_effect = RuntimeError("boom")
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"], profile="investor")

        # No partial shape - the whole recommendation (not just
        # horizon_1_week) is dropped, exactly like the trader profile.
        assert result == []

    def test_check_alerts_handles_missing_analysis(self):
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = None

        result = engine.check_alerts(["AAPL"])

        assert result == []

    def test_low_data_sufficiency_produces_no_trade_not_the_llm_signal(self):
        """Finding 3: decide(strict=True) can return normally with very
        few engines voting (data_sufficiency=0.2 means only 1 of 5
        voted) - that low-confidence-input output is treated the same
        as the exception path (NO_TRADE), not silently proceed."""
        engine = _make_engine(
            decision_engine=_make_decision_engine(decision=Prediction.SELL, confidence=0.9, data_sufficiency=0.2)
        )
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        engine.decision_engine.decide.assert_called_once_with("AAPL", strict=True)
        assert result == []

    def test_investor_profile_low_data_sufficiency_produces_no_trade(self):
        engine = _make_engine(
            decision_engine=_make_decision_engine(decision=Prediction.SELL, confidence=0.9, data_sufficiency=0.2)
        )
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"], profile="investor")

        assert result == []
