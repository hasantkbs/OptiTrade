"""
Unit tests for core/market_anomaly_detector.py — pure threshold logic,
no network calls, no LLM calls.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from core.market_anomaly_detector import MarketAlert, MarketAnomalyDetector
from core.regime_scanner import MarketRegime


def _analysis(volume_ratio=1.0, daily_return_pct=0.0, price_move_atr_multiple=0.0):
    return {
        "micro": {"volume_ratio": volume_ratio},
        "macro": {
            "daily_return_pct": daily_return_pct,
            "price_move_atr_multiple": price_move_atr_multiple,
        },
    }


def _news(impact_level=None, sentiment_score=0.0, sentiment_label="NEUTRAL"):
    if impact_level is None:
        return None
    return {
        "impact_level": impact_level,
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label,
    }


DETECTOR = MarketAnomalyDetector()


class TestNoTrigger:
    def test_calm_market_returns_none(self):
        result = DETECTOR.detect("AAPL", MarketRegime.RANGE_BOUND, _analysis(), None)
        assert result is None

    def test_missing_fields_default_safely(self):
        result = DETECTOR.detect("AAPL", MarketRegime.RANGE_BOUND, {}, None)
        assert result is None

    def test_low_impact_news_does_not_trigger(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.RANGE_BOUND, _analysis(),
            _news(impact_level="LOW", sentiment_score=0.1),
        )
        assert result is None


class TestPriceVolumeShock:
    def test_volume_ratio_above_threshold_triggers(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.TRENDING_BULL,
            _analysis(volume_ratio=3.5, daily_return_pct=2.0), None,
        )
        assert isinstance(result, MarketAlert)
        assert result.alert_type == "PRICE_VOLUME_SHOCK"
        assert result.severity == "MEDIUM"
        assert result.direction == "BULLISH"

    def test_atr_multiple_above_threshold_triggers_even_with_normal_volume(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.TRENDING_BEAR,
            _analysis(volume_ratio=1.0, daily_return_pct=-4.0, price_move_atr_multiple=3.0), None,
        )
        assert result is not None
        assert result.alert_type == "PRICE_VOLUME_SHOCK"
        assert result.direction == "BEARISH"

    def test_below_both_thresholds_does_not_trigger(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.RANGE_BOUND,
            _analysis(volume_ratio=1.4, daily_return_pct=0.5, price_move_atr_multiple=1.0), None,
        )
        assert result is None


class TestNewsShock:
    def test_high_impact_news_triggers(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.RANGE_BOUND, _analysis(),
            _news(impact_level="HIGH", sentiment_score=0.7, sentiment_label="POSITIVE"),
        )
        assert result is not None
        assert result.alert_type == "NEWS_SHOCK"
        assert result.severity == "MEDIUM"
        assert result.direction == "BULLISH"

    def test_high_impact_negative_news_is_bearish(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.RANGE_BOUND, _analysis(),
            _news(impact_level="HIGH", sentiment_score=-0.65, sentiment_label="NEGATIVE"),
        )
        assert result.direction == "BEARISH"


class TestCombined:
    def test_agreeing_signals_are_combined_high_severity(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.TRENDING_BULL,
            _analysis(volume_ratio=4.0, daily_return_pct=5.0),
            _news(impact_level="HIGH", sentiment_score=0.8, sentiment_label="POSITIVE"),
        )
        assert result.alert_type == "COMBINED"
        assert result.severity == "HIGH"
        assert result.direction == "BULLISH"

    def test_conflicting_signals_are_combined_neutral(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.TRENDING_BEAR,
            _analysis(volume_ratio=1.0, daily_return_pct=-3.0, price_move_atr_multiple=3.0),
            _news(impact_level="HIGH", sentiment_score=0.8, sentiment_label="POSITIVE"),
        )
        assert result.alert_type == "COMBINED"
        assert result.severity == "HIGH"
        assert result.direction == "NEUTRAL"
        assert "çelişiyor" in result.message


class TestMarketAlertShape:
    def test_details_includes_market_regime(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.CHOPPY_NO_OPPORTUNITY,
            _analysis(volume_ratio=5.0, daily_return_pct=1.0), None,
        )
        assert result.details["market_regime"] == "CHOPPY_NO_OPPORTUNITY"

    def test_symbol_is_set(self):
        result = DETECTOR.detect(
            "BTC-USD", MarketRegime.TRENDING_BULL,
            _analysis(volume_ratio=5.0, daily_return_pct=1.0), None,
        )
        assert result.symbol == "BTC-USD"
