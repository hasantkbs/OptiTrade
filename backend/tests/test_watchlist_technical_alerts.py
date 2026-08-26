"""Tests for watchlist/technical_alerts.py. Real PostgreSQL/Redis-backed
Feature Store, writing the exact feature names `engines.technical`
already computes."""
from datetime import datetime, timedelta, timezone

import pytest

from engines.technical.config import (
    FEATURE_ATR_PCT,
    FEATURE_BB_PERCENT_B,
    FEATURE_EMA_CROSSOVER,
    FEATURE_MACD_LINE,
    FEATURE_MACD_SIGNAL,
    FEATURE_RSI,
    FEATURE_VOLUME_RATIO,
)
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.technical_alerts import TechnicalAlertEvaluator

_SYMBOL = "WLTECHTEST"
_ALL_FEATURES = [
    FEATURE_RSI, FEATURE_MACD_LINE, FEATURE_MACD_SIGNAL, FEATURE_EMA_CROSSOVER,
    FEATURE_BB_PERCENT_B, FEATURE_VOLUME_RATIO, FEATURE_ATR_PCT,
]


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_SYMBOL,))
    finally:
        fs.offline_store._pool.putconn(conn)
    for name in _ALL_FEATURES:
        fs.online_store._client.delete(f"feature_store:{_SYMBOL}:{name}")


@pytest.fixture
def evaluator(feature_store):
    return TechnicalAlertEvaluator(feature_store=feature_store)


def _alert(alert_type, parameters=None, last_state=None):
    alert = Alert(
        owner="wl-tech-test", symbol=_SYMBOL, category=AlertCategory.TECHNICAL, alert_type=alert_type,
        parameters=parameters or {}, last_state=last_state or {},
    )
    alert.id = 1
    return alert


def test_rsi_overbought_triggers(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_RSI, value=80.0))
    event, state = evaluator.evaluate(_alert(AlertType.RSI_THRESHOLD))
    assert event is not None
    assert "overbought" in event.message
    assert state["rsi"] == 80.0


def test_rsi_oversold_triggers(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_RSI, value=20.0))
    event, _ = evaluator.evaluate(_alert(AlertType.RSI_THRESHOLD))
    assert event is not None
    assert "oversold" in event.message


def test_rsi_neutral_does_not_trigger(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_RSI, value=50.0))
    event, _ = evaluator.evaluate(_alert(AlertType.RSI_THRESHOLD))
    assert event is None


def test_rsi_raises_without_fresh_feature(evaluator):
    with pytest.raises(InsufficientAlertDataError):
        evaluator.evaluate(_alert(AlertType.RSI_THRESHOLD))


def test_macd_crossover_requires_a_prior_observation(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_MACD_LINE, value=0.5))
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_MACD_SIGNAL, value=1.0))
    event, state = evaluator.evaluate(_alert(AlertType.MACD_CROSSOVER))
    assert event is None  # no last_state yet - nothing to compare a crossover against
    assert state["macd_diff"] == pytest.approx(-0.5)


def test_macd_bullish_crossover_triggers(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_MACD_LINE, value=1.5))
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_MACD_SIGNAL, value=1.0))
    event, state = evaluator.evaluate(_alert(AlertType.MACD_CROSSOVER, last_state={"macd_diff": -1.0}))
    assert event is not None
    assert "bullish" in event.message
    assert state["macd_diff"] == pytest.approx(0.5)


def test_macd_no_crossover_when_diff_stays_same_sign(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_MACD_LINE, value=0.5))
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_MACD_SIGNAL, value=1.0))
    event, _ = evaluator.evaluate(_alert(AlertType.MACD_CROSSOVER, last_state={"macd_diff": -1.0}))
    assert event is None


def test_ema_golden_cross_triggers(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_EMA_CROSSOVER, value=2.0))
    event, _ = evaluator.evaluate(_alert(AlertType.EMA_CROSSOVER))
    assert event is not None
    assert "golden" in event.message


def test_ema_death_cross_triggers(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_EMA_CROSSOVER, value=-2.0))
    event, _ = evaluator.evaluate(_alert(AlertType.EMA_CROSSOVER))
    assert event is not None
    assert "death" in event.message


def test_ema_bullish_steady_state_does_not_trigger(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_EMA_CROSSOVER, value=1.0))
    event, _ = evaluator.evaluate(_alert(AlertType.EMA_CROSSOVER))
    assert event is None


def test_bollinger_breakout_above_upper_band(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_BB_PERCENT_B, value=1.2))
    event, _ = evaluator.evaluate(_alert(AlertType.BOLLINGER_BREAKOUT))
    assert event is not None
    assert "above" in event.message


def test_bollinger_breakout_below_lower_band(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_BB_PERCENT_B, value=-0.1))
    event, _ = evaluator.evaluate(_alert(AlertType.BOLLINGER_BREAKOUT))
    assert event is not None
    assert "below" in event.message


def test_volume_spike_triggers_above_ratio(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_VOLUME_RATIO, value=3.5))
    event, state = evaluator.evaluate(_alert(AlertType.VOLUME_SPIKE))
    assert event is not None
    assert state["volume_ratio"] == 3.5


def test_volume_spike_does_not_trigger_below_ratio(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_VOLUME_RATIO, value=1.2))
    event, _ = evaluator.evaluate(_alert(AlertType.VOLUME_SPIKE))
    assert event is None


def test_atr_expansion_triggers_above_baseline(feature_store, evaluator):
    now = datetime.now(timezone.utc)
    for i in range(14):
        feature_store.write_feature(
            FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_ATR_PCT, value=2.0, event_timestamp=now - timedelta(days=14 - i))
        )
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_ATR_PCT, value=6.0, event_timestamp=now))
    event, state = evaluator.evaluate(_alert(AlertType.ATR_EXPANSION))
    assert event is not None
    assert state["atr_pct"] == 6.0
    assert state["atr_baseline_pct"] == pytest.approx(2.0)


def test_atr_expansion_raises_with_insufficient_history(feature_store, evaluator):
    feature_store.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_ATR_PCT, value=2.0))
    with pytest.raises(InsufficientAlertDataError):
        evaluator.evaluate(_alert(AlertType.ATR_EXPANSION))


def test_raises_for_wrong_category(evaluator):
    alert = _alert(AlertType.RSI_THRESHOLD)
    alert.category = AlertCategory.PRICE
    with pytest.raises(InvalidAlertError):
        evaluator.evaluate(alert)


def test_service_defaults_to_real_dependencies():
    evaluator = TechnicalAlertEvaluator()
    assert isinstance(evaluator.feature_store, FeatureStoreService)
