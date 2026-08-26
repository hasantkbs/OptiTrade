"""Tests for decision_engine/config.py and decision_engine/exceptions.py."""
from decision_engine.config import DecisionEngineConfig
from decision_engine.exceptions import (
    DecisionEngineError,
    ExecutionPersistenceError,
    NoValidVotesError,
)


def test_from_env_reads_configured_values(monkeypatch):
    monkeypatch.setenv("DECISION_ENGINE_DEFAULT_ACCURACY_WEIGHT", "0.75")
    monkeypatch.setenv("DECISION_ENGINE_AGGREGATION_STRATEGY_VERSION", "custom_v3")
    monkeypatch.setenv("DECISION_ENGINE_ACCURACY_FEATURE_NAME", "my_accuracy")

    config = DecisionEngineConfig.from_env()

    assert config.default_accuracy_weight == 0.75
    assert config.aggregation_strategy_version == "custom_v3"
    assert config.accuracy_feature_name == "my_accuracy"


def test_from_env_defaults_when_unset(monkeypatch):
    for key in (
        "DECISION_ENGINE_DEFAULT_ACCURACY_WEIGHT",
        "DECISION_ENGINE_AGGREGATION_STRATEGY_VERSION",
        "DECISION_ENGINE_ACCURACY_FEATURE_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    config = DecisionEngineConfig.from_env()

    assert config.default_accuracy_weight == 1.0
    assert config.aggregation_strategy_version == "accuracy_weighted_v1"
    assert config.accuracy_feature_name == "engine_accuracy_score"


def test_config_is_frozen():
    config = DecisionEngineConfig()
    try:
        config.default_accuracy_weight = 5.0  # type: ignore[misc]
        assert False, "expected an error assigning to a frozen dataclass"
    except AttributeError:
        pass


def test_no_valid_votes_error_message():
    exc = NoValidVotesError("BTC-USD")
    assert exc.symbol == "BTC-USD"
    assert "BTC-USD" in str(exc)
    assert isinstance(exc, DecisionEngineError)


def test_execution_persistence_error_is_a_decision_engine_error():
    assert issubclass(ExecutionPersistenceError, DecisionEngineError)
