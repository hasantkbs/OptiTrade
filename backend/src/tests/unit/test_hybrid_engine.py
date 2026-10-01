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
from core.regime_scanner import MarketRegime, ScannedSymbol
from core.risk_manager import RiskLevels
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
    return TradeRecommendation(
        symbol=symbol, market_regime="TRENDING_BULL",
        trader_analysis="a", investor_analysis="b",
        signal=TradeSignal.BUY, confidence_score=70,
        entry_price=180.0, stop_loss=175.0, take_profit_1=185.0, take_profit_2=190.0,
        trader_commentary="c",
    )


def _investor_rec(symbol="AAPL"):
    horizon = HorizonView(signal=TradeSignal.BUY, confidence_score=60, rationale="r")
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


def _decision_output(symbol="AAPL", decision=Prediction.BUY, confidence=0.70):
    """Default (BUY, 0.70) is deliberately chosen to map onto the exact
    same (TradeSignal.BUY, confidence_score=70) `_trade_rec()` already
    hardcodes - so `_apply_canonical_decision`'s override is a no-op for
    every pre-existing exact-equality assertion (`result == [_trade_rec()]`)
    below, and only the dedicated Decision Engine tests further down
    need a differing value to prove the override actually happens."""
    return DecisionOutput(
        symbol=symbol, decision=decision, confidence=confidence,
        expected_return=0.01, expected_volatility=0.02,
        aggregation_strategy_version="test", data_sufficiency=1.0,
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

        assert result == [_trade_rec()]
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
        # confidence=0.60 (not the shared _decision_output default of
        # 0.70) is deliberately chosen to map onto the exact same
        # (TradeSignal.BUY, confidence_score=60) _investor_rec()'s
        # horizon_1_week already hardcodes - so
        # _apply_canonical_decision_to_investor_horizon's override is a
        # no-op here, and this test can keep asserting plain equality
        # against the LLM's own untouched recommendation. The dedicated
        # TestCanonicalDecisionOverride tests below prove the override
        # itself.
        engine = _make_engine(decision_engine=_make_decision_engine(confidence=0.60))
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"], profile="investor")

        assert result == [_investor_rec()]
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


class TestCanonicalDecisionOverride:
    """The Decision Engine is the single decision authority for
    profile="trader" - the LLM's own signal/confidence_score must never
    reach the caller unmodified (gap-analysis.md section 2)."""

    def test_decision_engine_output_overrides_the_llm_signal(self):
        engine = _make_engine(decision_engine=_make_decision_engine(decision=Prediction.SELL, confidence=0.9))
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()  # says BUY/70
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        engine.decision_engine.decide.assert_called_once_with("AAPL", strict=True)
        assert result[0].signal == TradeSignal.STRONG_SELL  # 0.9 crosses the "strong" bar
        assert result[0].confidence_score == 90
        assert result[0].entry_price == 180.0  # risk_manager-sourced, unaffected

    def test_decision_engine_failure_falls_back_to_the_llm_signal(self):
        engine = _make_engine()
        engine.decision_engine.decide.side_effect = RuntimeError("boom")
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()  # says BUY/70
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        assert result == [_trade_rec()]  # unchanged - LLM's own signal survives

    def test_investor_profile_1_week_horizon_is_overridden_by_the_decision_engine(self):
        """decision_engine has no per-horizon concept, so only
        horizon_1_week (closest match to a current-conditions vote) is
        overridden; horizon_1_month/horizon_1_year stay exactly as the
        LLM (investor_persona) produced them."""
        engine = _make_engine(decision_engine=_make_decision_engine(decision=Prediction.SELL, confidence=0.9))
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()  # all horizons say BUY/60
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"], profile="investor")

        engine.decision_engine.decide.assert_called_once_with("AAPL", strict=True)
        rec = result[0]
        assert rec.horizon_1_week.signal == TradeSignal.STRONG_SELL  # 0.9 crosses the "strong" bar
        assert rec.horizon_1_week.confidence_score == 90
        assert rec.horizon_1_month.signal == TradeSignal.BUY
        assert rec.horizon_1_month.confidence_score == 60
        assert rec.horizon_1_year.signal == TradeSignal.BUY
        assert rec.horizon_1_year.confidence_score == 60
        assert engine.analyzer.analyze.call_count == 1  # run() sırasında çekilen veri yeniden kullanıldı

    def test_investor_profile_falls_back_to_llm_horizon_1_week_when_decision_engine_fails(self):
        engine = _make_engine()
        engine.decision_engine.decide.side_effect = RuntimeError("boom")
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"], profile="investor")

        # Decision Engine blew up - horizon_1_week keeps the LLM's own
        # (uncorroborated) signal/confidence_score.
        assert result[0].horizon_1_week.signal == TradeSignal.BUY
        assert result[0].horizon_1_week.confidence_score == 60

    def test_check_alerts_handles_missing_analysis(self):
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = None

        result = engine.check_alerts(["AAPL"])

        assert result == []
