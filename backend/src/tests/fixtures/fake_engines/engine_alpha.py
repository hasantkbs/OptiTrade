"""Fixture: a fake self-registering voting engine, imported by
engine_registry's discovery tests. Registers itself into the shared
`default_registry` as a side effect of being imported, per the
self-registration convention documented in
`engine_registry/discovery.py`."""
from decision_engine.models import EngineVote, Prediction
from engine_registry.registry import default_registry


class FakeEngineAlpha:
    engine_name = "FakeEngineAlpha"
    engine_version = "v1"

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=Prediction.BUY, confidence=0.7,
            expected_return=1.0, volatility=1.0,
        )


default_registry.register(FakeEngineAlpha())
