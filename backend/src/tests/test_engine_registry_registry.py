"""Tests for engine_registry/registry.py."""
import pytest

from decision_engine.models import EngineVote, Prediction
from engine_registry.exceptions import DuplicateEngineError, EngineNotFoundError, IncompatibleEngineError
from engine_registry.registry import EngineRegistry


class FakeEngine:
    def __init__(self, name="TechnicalEngine", version="v1"):
        self.engine_name = name
        self.engine_version = version

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=Prediction.HOLD, confidence=0.5,
            expected_return=0.0, volatility=1.0,
        )


class NotAnEngine:
    """Deliberately missing engine_name/engine_version/vote()."""


def test_new_registry_is_empty():
    registry = EngineRegistry()
    assert len(registry) == 0
    assert registry.all() == []


def test_register_adds_an_engine_enabled_by_default():
    registry = EngineRegistry()
    engine = FakeEngine()
    registry.register(engine)
    assert len(registry) == 1
    assert registry.is_enabled("TechnicalEngine", "v1") is True


def test_register_rejects_an_incompatible_object():
    registry = EngineRegistry()
    with pytest.raises(IncompatibleEngineError):
        registry.register(NotAnEngine())
    assert len(registry) == 0


def test_register_rejects_exact_duplicate_name_and_version():
    registry = EngineRegistry()
    registry.register(FakeEngine("TechnicalEngine", "v1"))
    with pytest.raises(DuplicateEngineError):
        registry.register(FakeEngine("TechnicalEngine", "v1"))
    assert len(registry) == 1


def test_register_allows_a_different_version_of_the_same_engine_name():
    registry = EngineRegistry()
    registry.register(FakeEngine("TechnicalEngine", "v1"))
    registry.register(FakeEngine("TechnicalEngine", "v2"))
    assert len(registry) == 2
    assert set(registry.versions_of("TechnicalEngine")) == {"v1", "v2"}


def test_get_returns_the_registered_engine():
    registry = EngineRegistry()
    engine = FakeEngine()
    registry.register(engine)
    assert registry.get("TechnicalEngine", "v1") is engine


def test_get_raises_for_an_unregistered_engine():
    registry = EngineRegistry()
    with pytest.raises(EngineNotFoundError):
        registry.get("DoesNotExist", "v1")


def test_unregister_removes_the_engine():
    registry = EngineRegistry()
    registry.register(FakeEngine())
    registry.unregister("TechnicalEngine", "v1")
    assert len(registry) == 0
    with pytest.raises(EngineNotFoundError):
        registry.get("TechnicalEngine", "v1")


def test_unregister_raises_for_an_unregistered_engine():
    registry = EngineRegistry()
    with pytest.raises(EngineNotFoundError):
        registry.unregister("DoesNotExist", "v1")


def test_disable_then_enable_round_trips():
    registry = EngineRegistry()
    registry.register(FakeEngine())
    registry.disable("TechnicalEngine", "v1")
    assert registry.is_enabled("TechnicalEngine", "v1") is False
    registry.enable("TechnicalEngine", "v1")
    assert registry.is_enabled("TechnicalEngine", "v1") is True


def test_enable_raises_for_an_unregistered_engine():
    registry = EngineRegistry()
    with pytest.raises(EngineNotFoundError):
        registry.enable("DoesNotExist", "v1")


def test_disable_raises_for_an_unregistered_engine():
    registry = EngineRegistry()
    with pytest.raises(EngineNotFoundError):
        registry.disable("DoesNotExist", "v1")


def test_is_enabled_raises_for_an_unregistered_engine():
    registry = EngineRegistry()
    with pytest.raises(EngineNotFoundError):
        registry.is_enabled("DoesNotExist", "v1")


def test_all_includes_disabled_engines():
    registry = EngineRegistry()
    registry.register(FakeEngine())
    registry.disable("TechnicalEngine", "v1")
    assert len(registry.all()) == 1


def test_all_enabled_excludes_disabled_engines():
    registry = EngineRegistry()
    registry.register(FakeEngine("A", "v1"))
    registry.register(FakeEngine("B", "v1"))
    registry.disable("B", "v1")
    enabled_names = {e.engine_name for e in registry.all_enabled()}
    assert enabled_names == {"A"}


def test_clear_removes_everything():
    registry = EngineRegistry()
    registry.register(FakeEngine("A", "v1"))
    registry.register(FakeEngine("B", "v1"))
    registry.clear()
    assert len(registry) == 0
