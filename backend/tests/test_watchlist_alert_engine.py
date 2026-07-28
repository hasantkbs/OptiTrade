"""Tests for watchlist/alert_engine.py. Real Feature Store for
technical-category dispatch; a fake `pipeline_service` stands in for
`pipeline.service.PipelineService` (which is expensive to construct and
hits live network/LLM calls) for Decision Engine alert coverage."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from decision_engine.models import Prediction
from watchlist.alert_engine import AlertEngine
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.price_alerts import PriceAlertEvaluator


class _FakeEngineBreakdownItem:
    def __init__(self, engine_name, engine_version, status="success"):
        self.engine_name = engine_name
        self.engine_version = engine_version

        class _Status:
            def __init__(self, value):
                self.value = value

        self.status = _Status(status)


class _FakePipelineResponse:
    def __init__(self, decision, confidence, expected_return=5.0, expected_volatility=12.0):
        self.decision = decision
        self.confidence = confidence
        self.expected_return = expected_return
        self.expected_volatility = expected_volatility
        self.engine_breakdown = [_FakeEngineBreakdownItem("TechnicalEngine", "v1")]


class _FakePipelineService:
    def __init__(self, response):
        self._response = response

    def run(self, symbol):
        return self._response


def _decision_alert(alert_type, parameters=None, last_state=None):
    alert = Alert(
        owner="wl-engine-test", symbol="AAPL", category=AlertCategory.DECISION, alert_type=alert_type,
        parameters=parameters or {}, last_state=last_state or {},
    )
    alert.id = 1
    return alert


def test_evaluate_dispatches_price_alerts_to_price_evaluator():
    def fake_fetcher(symbol, period="5d"):
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=2, freq="D", tz="UTC")
        return pd.DataFrame({"Close": [100, 210]}, index=dates)

    engine = AlertEngine(price_evaluator=PriceAlertEvaluator(price_fetcher=fake_fetcher))
    alert = Alert(
        owner="wl-engine-test", symbol="AAPL", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE,
        parameters={"threshold": 200.0},
    )
    alert.id = 1
    event, _ = engine.evaluate(alert)
    assert event is not None


def test_evaluate_raises_for_decision_alert_without_pipeline_service():
    engine = AlertEngine(pipeline_service=None)
    with pytest.raises(InsufficientAlertDataError):
        engine.evaluate(_decision_alert(AlertType.DECISION_BUY))


def test_evaluate_raises_for_decision_alert_without_symbol():
    engine = AlertEngine(pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.BUY, 0.8)))
    alert = _decision_alert(AlertType.DECISION_BUY)
    alert.symbol = None
    with pytest.raises(InvalidAlertError):
        engine.evaluate(alert)


def test_decision_buy_appears_on_first_observation():
    engine = AlertEngine(pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.BUY, 0.8)))
    event, state = engine.evaluate(_decision_alert(AlertType.DECISION_BUY))
    assert event is not None
    assert event.related_decision == Prediction.BUY
    assert state["decision"] == 1.0


def test_decision_buy_does_not_re_fire_when_already_buy():
    engine = AlertEngine(pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.BUY, 0.8)))
    event, _ = engine.evaluate(_decision_alert(AlertType.DECISION_BUY, last_state={"decision": 1.0}))
    assert event is None


def test_decision_buy_does_not_fire_when_decision_is_sell():
    engine = AlertEngine(pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.SELL, 0.8)))
    event, state = engine.evaluate(_decision_alert(AlertType.DECISION_BUY))
    assert event is None
    assert state["decision"] == -1.0


def test_decision_sell_appears():
    engine = AlertEngine(pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.SELL, 0.9)))
    event, _ = engine.evaluate(_decision_alert(AlertType.DECISION_SELL, last_state={"decision": 0.0}))
    assert event is not None
    assert event.related_decision == Prediction.SELL


def test_confidence_change_requires_prior_observation():
    engine = AlertEngine(pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.HOLD, 0.8)))
    event, state = engine.evaluate(_decision_alert(AlertType.CONFIDENCE_CHANGE))
    assert event is None  # first observation - nothing to compare
    assert state["confidence"] == 0.8


def test_confidence_change_triggers_above_threshold():
    engine = AlertEngine(pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.HOLD, 0.8)))
    event, _ = engine.evaluate(_decision_alert(AlertType.CONFIDENCE_CHANGE, last_state={"confidence": 0.2}))
    assert event is not None
    assert "confidence" in event.message


def test_confidence_change_does_not_trigger_for_small_delta():
    engine = AlertEngine(pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.HOLD, 0.51)))
    event, _ = engine.evaluate(_decision_alert(AlertType.CONFIDENCE_CHANGE, last_state={"confidence": 0.5}))
    assert event is None


def test_expected_return_change_triggers_above_threshold():
    engine = AlertEngine(
        pipeline_service=_FakePipelineService(_FakePipelineResponse(Prediction.BUY, 0.8, expected_return=10.0)),
    )
    event, _ = engine.evaluate(
        _decision_alert(AlertType.EXPECTED_RETURN_CHANGE, last_state={"expected_return": 1.0}),
    )
    assert event is not None


def test_risk_change_triggers_above_threshold():
    engine = AlertEngine(
        pipeline_service=_FakePipelineService(
            _FakePipelineResponse(Prediction.BUY, 0.8, expected_volatility=30.0),
        ),
    )
    event, _ = engine.evaluate(_decision_alert(AlertType.RISK_CHANGE, last_state={"expected_volatility": 10.0}))
    assert event is not None


def test_evaluate_raises_for_unknown_category():
    engine = AlertEngine()
    alert = _decision_alert(AlertType.DECISION_BUY)
    alert.category = "not-a-real-category"
    with pytest.raises(InvalidAlertError):
        engine.evaluate(alert)


def test_service_defaults_to_real_dependencies():
    engine = AlertEngine()
    assert engine.pipeline_service is None
