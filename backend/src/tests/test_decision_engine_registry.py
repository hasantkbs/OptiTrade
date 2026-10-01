"""Tests for decision_engine/registry.py."""
from decision_engine.models import EngineVote, Prediction
from decision_engine.registry import VotingEngineRegistry


class FakeEngine:
    engine_name = "FakeEngine"
    engine_version = "v1"

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=Prediction.HOLD, confidence=0.5,
            expected_return=0.0, volatility=1.0,
        )


def test_new_registry_is_empty():
    registry = VotingEngineRegistry()
    assert registry.all() == []
    assert len(registry) == 0


def test_register_adds_an_engine():
    registry = VotingEngineRegistry()
    engine = FakeEngine()
    registry.register(engine)
    assert registry.all() == [engine]
    assert len(registry) == 1


def test_register_preserves_registration_order():
    registry = VotingEngineRegistry()
    first, second = FakeEngine(), FakeEngine()
    registry.register(first)
    registry.register(second)
    assert registry.all() == [first, second]


def test_all_returns_a_copy_not_the_internal_list():
    registry = VotingEngineRegistry()
    registry.register(FakeEngine())
    snapshot = registry.all()
    snapshot.append(FakeEngine())
    assert len(registry) == 1  # mutating the snapshot didn't affect the registry
