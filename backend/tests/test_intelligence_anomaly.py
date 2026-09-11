"""
Unit tests for intelligence/anomaly.py - the canonical
`MarketAnomalyDetector` (extracted from `core.market_anomaly_detector`,
which now re-exports this module unchanged - see
`test_market_anomaly_detector_shim.py` for that guarantee, and
`tests/test_market_anomaly_detector.py` / `tests/unit/test_market_anomaly_detector.py`
for the pre-existing, still-passing exhaustive threshold/boundary/
malformed-input coverage this extraction did not need to duplicate).

Pure threshold logic - no network calls, no LLM calls.
"""
from intelligence.anomaly import MarketAlert, MarketAnomalyDetector
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


def test_normal_market_conditions_produce_no_alert():
    result = DETECTOR.detect("AAPL", MarketRegime.RANGE_BOUND, _analysis(), None)
    assert result is None


def test_price_volume_shock_detected():
    result = DETECTOR.detect(
        "AAPL", MarketRegime.TRENDING_BULL,
        _analysis(volume_ratio=3.5, daily_return_pct=2.0), None,
    )
    assert isinstance(result, MarketAlert)
    assert result.alert_type == "PRICE_VOLUME_SHOCK"
    assert result.severity == "MEDIUM"
    assert result.direction == "BULLISH"


def test_volume_shock_alone_detected():
    result = DETECTOR.detect(
        "AAPL", MarketRegime.TRENDING_BEAR,
        _analysis(volume_ratio=4.0, daily_return_pct=-3.0, price_move_atr_multiple=0.5), None,
    )
    assert result is not None
    assert result.alert_type == "PRICE_VOLUME_SHOCK"
    assert result.direction == "BEARISH"


def test_news_shock_detected():
    result = DETECTOR.detect(
        "AAPL", MarketRegime.RANGE_BOUND, _analysis(),
        _news(impact_level="HIGH", sentiment_score=0.7, sentiment_label="POSITIVE"),
    )
    assert result is not None
    assert result.alert_type == "NEWS_SHOCK"
    assert result.direction == "BULLISH"


def test_low_impact_news_does_not_trigger():
    result = DETECTOR.detect(
        "AAPL", MarketRegime.RANGE_BOUND, _analysis(),
        _news(impact_level="LOW", sentiment_score=0.1),
    )
    assert result is None


def test_combined_price_and_news_shock():
    result = DETECTOR.detect(
        "AAPL", MarketRegime.TRENDING_BULL,
        _analysis(volume_ratio=4.0, daily_return_pct=5.0),
        _news(impact_level="HIGH", sentiment_score=0.8, sentiment_label="POSITIVE"),
    )
    assert result.alert_type == "COMBINED"
    assert result.severity == "HIGH"
    assert result.direction == "BULLISH"


def test_deterministic_for_identical_inputs():
    """Same inputs must always produce the same result - no randomness,
    no LLM, no hidden state carried between calls."""
    analysis = _analysis(volume_ratio=3.5, daily_return_pct=2.0)
    first = DETECTOR.detect("AAPL", MarketRegime.TRENDING_BULL, analysis, None)
    second = DETECTOR.detect("AAPL", MarketRegime.TRENDING_BULL, analysis, None)

    assert first.model_dump(exclude={"detected_at"}) == second.model_dump(exclude={"detected_at"})


def test_malformed_input_degrades_to_none_not_an_exception():
    result = DETECTOR.detect("AAPL", MarketRegime.RANGE_BOUND, None, None)
    assert result is None
