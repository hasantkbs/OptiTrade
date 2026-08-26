"""Tests for engine_registry/executor.py."""
import pytest

from decision_engine.models import EngineVote, Prediction
from engine_registry.exceptions import EngineNotFoundError
from engine_registry.executor import execute_all, execute_one
from engine_registry.models import ExecutionStatus
from engine_registry.registry import EngineRegistry


class FakeEngine:
    def __init__(self, name="TechnicalEngine", version="v1", raises=False):
        self.engine_name = name
        self.engine_version = version
        self._raises = raises
        self.calls = []

    def vote(self, symbol: str) -> EngineVote:
        self.calls.append(symbol)
        if self._raises:
            raise RuntimeError("simulated failure")
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=Prediction.BUY, confidence=0.8,
            expected_return=1.0, volatility=1.0,
        )


def test_execute_one_returns_success_metadata_and_the_vote():
    registry = EngineRegistry()
    registry.register(FakeEngine())

    result = execute_one(registry, "TechnicalEngine", "v1", "BTC-USD")

    assert result.status == ExecutionStatus.SUCCESS
    assert result.engine_name == "TechnicalEngine"
    assert result.engine_version == "v1"
    assert result.vote is not None
    assert result.vote.prediction == Prediction.BUY
    assert result.duration_ms >= 0.0
    assert result.error_type is None


def test_execute_one_returns_failure_metadata_when_the_engine_raises():
    registry = EngineRegistry()
    registry.register(FakeEngine(raises=True))

    result = execute_one(registry, "TechnicalEngine", "v1", "BTC-USD")

    assert result.status == ExecutionStatus.FAILURE
    assert result.error_type == "RuntimeError"
    assert result.vote is None


def test_execute_one_returns_disabled_metadata_without_calling_vote():
    registry = EngineRegistry()
    engine = FakeEngine()
    registry.register(engine)
    registry.disable("TechnicalEngine", "v1")

    result = execute_one(registry, "TechnicalEngine", "v1", "BTC-USD")

    assert result.status == ExecutionStatus.DISABLED
    assert engine.calls == []  # vote() was never called


def test_execute_one_raises_for_an_unregistered_engine():
    registry = EngineRegistry()
    with pytest.raises(EngineNotFoundError):
        execute_one(registry, "DoesNotExist", "v1", "BTC-USD")


def test_execute_all_runs_every_registered_engine():
    registry = EngineRegistry()
    registry.register(FakeEngine("A", "v1"))
    registry.register(FakeEngine("B", "v1"))

    results = execute_all(registry, "BTC-USD")

    assert len(results) == 2
    assert {r.engine_name for r in results} == {"A", "B"}
    assert all(r.status == ExecutionStatus.SUCCESS for r in results)


def test_execute_all_includes_disabled_engines_with_disabled_status():
    registry = EngineRegistry()
    registry.register(FakeEngine("A", "v1"))
    registry.register(FakeEngine("B", "v1"))
    registry.disable("B", "v1")

    results = execute_all(registry, "BTC-USD")

    by_name = {r.engine_name: r.status for r in results}
    assert by_name["A"] == ExecutionStatus.SUCCESS
    assert by_name["B"] == ExecutionStatus.DISABLED


def test_execute_all_isolates_one_engines_failure_from_the_rest():
    registry = EngineRegistry()
    registry.register(FakeEngine("Good", "v1"))
    registry.register(FakeEngine("Bad", "v1", raises=True))

    results = execute_all(registry, "BTC-USD")

    by_name = {r.engine_name: r.status for r in results}
    assert by_name["Good"] == ExecutionStatus.SUCCESS
    assert by_name["Bad"] == ExecutionStatus.FAILURE


def test_execute_all_on_empty_registry_returns_empty_list():
    assert execute_all(EngineRegistry(), "BTC-USD") == []
