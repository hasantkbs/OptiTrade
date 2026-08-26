"""Tests for watchlist/notification_router.py. No infra needed - this
module has no persistence of its own, and its only concrete provider
(InMemoryNotificationProvider) makes no external call."""
from decision_engine.models import Prediction
from watchlist.models import AlertCategory, AlertSeverity, AlertTriggerEvent, AlertType
from watchlist.notification_router import InMemoryNotificationProvider, NotificationRouter


def _event(**overrides) -> AlertTriggerEvent:
    defaults = dict(
        alert_id=1, owner="wl-notify-test", symbol="AAPL", category=AlertCategory.PRICE,
        alert_type=AlertType.PRICE_ABOVE, message="AAPL above 200", evidence={"price": 210.0},
    )
    defaults.update(overrides)
    return AlertTriggerEvent(**defaults)


def test_build_payload_includes_category_and_symbol():
    router = NotificationRouter(providers=[])
    payload = router.build_payload(_event())
    assert payload.title == "Price Alert: AAPL"
    assert payload.body == "AAPL above 200"
    assert payload.data["category"] == "price"
    assert payload.data["alert_type"] == "price_above"
    assert payload.data["symbol"] == "AAPL"


def test_build_payload_without_symbol_omits_it_from_title_and_data():
    router = NotificationRouter(providers=[])
    payload = router.build_payload(_event(symbol=None, category=AlertCategory.PORTFOLIO, portfolio_id=5))
    assert payload.title == "Portfolio Alert"
    assert "symbol" not in payload.data
    assert payload.data["portfolio_id"] == "5"


def test_build_payload_includes_related_decision():
    router = NotificationRouter(providers=[])
    payload = router.build_payload(_event(category=AlertCategory.DECISION, related_decision=Prediction.BUY))
    assert payload.data["decision"] == "BUY"


def test_route_sends_to_every_registered_provider():
    provider_a, provider_b = InMemoryNotificationProvider(), InMemoryNotificationProvider()
    router = NotificationRouter(providers=[provider_a, provider_b])
    router.route(_event())
    assert len(provider_a.sent) == 1
    assert len(provider_b.sent) == 1
    assert provider_a.sent[0].alert_id == 1


def test_route_continues_when_one_provider_raises():
    class _BrokenProvider:
        def send(self, payload):
            raise RuntimeError("boom")

    working_provider = InMemoryNotificationProvider()
    router = NotificationRouter(providers=[_BrokenProvider(), working_provider])
    payload = router.route(_event())
    assert payload is not None
    assert len(working_provider.sent) == 1


def test_severity_is_carried_through_to_the_payload():
    router = NotificationRouter(providers=[])
    payload = router.build_payload(_event(severity=AlertSeverity.CRITICAL))
    assert payload.severity == AlertSeverity.CRITICAL


def test_default_provider_list_is_an_in_memory_provider():
    router = NotificationRouter()
    assert len(router.providers) == 1
    assert isinstance(router.providers[0], InMemoryNotificationProvider)
