"""Tests for learning/config.py."""
from learning.config import LearningConfig
from learning.models import WeightingPolicy


def test_default_config_values():
    config = LearningConfig()
    assert config.evaluation_horizon_days == 5
    assert config.weighting_policy == WeightingPolicy.EXPONENTIAL_DECAY
    assert config.baseline_accuracy == 0.5


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("LEARNING_EVALUATION_HORIZON_DAYS", "10")
    monkeypatch.setenv("LEARNING_WEIGHTING_POLICY", "bayesian")
    monkeypatch.setenv("LEARNING_MAX_WEIGHT_STEP", "0.05")
    config = LearningConfig.from_env()
    assert config.evaluation_horizon_days == 10
    assert config.weighting_policy == WeightingPolicy.BAYESIAN
    assert config.max_weight_step == 0.05


def test_from_env_defaults_when_unset(monkeypatch):
    for var in ["LEARNING_EVALUATION_HORIZON_DAYS", "LEARNING_WEIGHTING_POLICY"]:
        monkeypatch.delenv(var, raising=False)
    config = LearningConfig.from_env()
    assert config.evaluation_horizon_days == 5
    assert config.weighting_policy == WeightingPolicy.EXPONENTIAL_DECAY


def test_config_is_frozen():
    config = LearningConfig()
    with_exception = False
    try:
        config.evaluation_horizon_days = 99
    except Exception:
        with_exception = True
    assert with_exception
