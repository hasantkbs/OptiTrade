"""Fixture: a second fake self-registering voting engine (see
engine_alpha.py's docstring)."""
from decision_engine.models import EngineVote, Prediction
from engine_registry.registry import default_registry


class FakeEngineBeta:
    engine_name = "FakeEngineBeta"
    engine_version = "v1"

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=Prediction.SELL, confidence=0.6,
            expected_return=-0.5, volatility=1.2,
        )


default_registry.register(FakeEngineBeta())
