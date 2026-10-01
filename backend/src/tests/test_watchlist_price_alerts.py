"""Tests for watchlist/price_alerts.py. Deterministic fake price
fetcher - no real infra needed (this evaluator has no persistence of
its own)."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.price_alerts import PriceAlertEvaluator


def _history(closes, opens=None):
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=len(closes), freq="D", tz="UTC")
    data = {"Close": closes}
    if opens is not None:
        data["Open"] = opens
    return pd.DataFrame(data, index=dates)


def _alert(alert_type, parameters=None, symbol="AAPL"):
    alert = Alert(
        owner="wl-price-test", symbol=symbol, category=AlertCategory.PRICE, alert_type=alert_type,
        parameters=parameters or {},
    )
    alert.id = 1
    return alert


def _evaluator(fetcher):
    return PriceAlertEvaluator(price_fetcher=fetcher)


def test_price_above_triggers_when_exceeding_threshold():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100, 105, 210]))
    event, state = evaluator.evaluate(_alert(AlertType.PRICE_ABOVE, {"threshold": 200.0}))
    assert event is not None
    assert "above" in event.message
    assert state["last_price"] == 210.0


def test_price_above_does_not_trigger_when_below_threshold():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100, 105, 110]))
    event, _ = evaluator.evaluate(_alert(AlertType.PRICE_ABOVE, {"threshold": 200.0}))
    assert event is None


def test_price_below_triggers_when_under_threshold():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100, 90, 80]))
    event, _ = evaluator.evaluate(_alert(AlertType.PRICE_BELOW, {"threshold": 100.0}))
    assert event is not None
    assert "below" in event.message


def test_price_above_requires_threshold_parameter():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100]))
    with pytest.raises(InvalidAlertError):
        evaluator.evaluate(_alert(AlertType.PRICE_ABOVE, {}))


def test_price_percent_move_triggers_on_large_move():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100, 100, 110]))
    event, state = evaluator.evaluate(_alert(AlertType.PRICE_PERCENT_MOVE, {"threshold_pct": 5.0}))
    assert event is not None
    assert state["change_pct"] == pytest.approx(10.0)


def test_price_percent_move_does_not_trigger_on_small_move():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100, 100, 101]))
    event, _ = evaluator.evaluate(_alert(AlertType.PRICE_PERCENT_MOVE, {"threshold_pct": 5.0}))
    assert event is None


def test_price_percent_move_requires_at_least_two_days_of_history():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100]))
    with pytest.raises(InsufficientAlertDataError):
        evaluator.evaluate(_alert(AlertType.PRICE_PERCENT_MOVE))


def test_price_gap_triggers_on_a_large_open_gap():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100, 100], opens=[100, 110]))
    event, state = evaluator.evaluate(_alert(AlertType.PRICE_GAP, {"threshold_pct": 3.0}))
    assert event is not None
    assert state["gap_pct"] == pytest.approx(10.0)


def test_price_gap_does_not_trigger_on_a_small_gap():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100, 100], opens=[100, 101]))
    event, _ = evaluator.evaluate(_alert(AlertType.PRICE_GAP, {"threshold_pct": 3.0}))
    assert event is None


def test_raises_for_missing_price_data():
    evaluator = _evaluator(lambda symbol, period="5d": pd.DataFrame())
    with pytest.raises(InsufficientAlertDataError):
        evaluator.evaluate(_alert(AlertType.PRICE_ABOVE, {"threshold": 100.0}))


def test_raises_for_wrong_category():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100]))
    alert = _alert(AlertType.PRICE_ABOVE, {"threshold": 1.0})
    alert.category = AlertCategory.TECHNICAL
    with pytest.raises(InvalidAlertError):
        evaluator.evaluate(alert)


def test_raises_for_missing_symbol():
    evaluator = _evaluator(lambda symbol, period="5d": _history([100]))
    alert = _alert(AlertType.PRICE_ABOVE, {"threshold": 1.0})
    alert.symbol = None
    with pytest.raises(InvalidAlertError):
        evaluator.evaluate(alert)


def test_service_defaults_to_real_dependencies():
    evaluator = PriceAlertEvaluator()
    assert evaluator.price_fetcher is not None
