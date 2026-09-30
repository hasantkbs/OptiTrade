"""Tests for ml_training/config.py."""
from ml_training.config import MLTrainingConfig


def test_default_config_values():
    config = MLTrainingConfig()
    assert config.trader_horizons_days == [1, 3, 5]
    assert config.investor_horizons_days == [30, 90, 180]
    assert config.proximity_threshold_pct == 2.0


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("ML_TRAINING_TRADER_HORIZONS_DAYS", "2,4,6")
    monkeypatch.setenv("ML_TRAINING_OPTUNA_N_TRIALS", "10")
    config = MLTrainingConfig.from_env()
    assert config.trader_horizons_days == [2, 4, 6]
    assert config.optuna_n_trials == 10


def test_from_env_defaults_when_unset(monkeypatch):
    for var in ["ML_TRAINING_TRADER_HORIZONS_DAYS", "ML_TRAINING_OPTUNA_N_TRIALS"]:
        monkeypatch.delenv(var, raising=False)
    config = MLTrainingConfig.from_env()
    assert config.trader_horizons_days == [1, 3, 5]
    assert config.optuna_n_trials == 50


def test_config_is_frozen():
    config = MLTrainingConfig()
    raised = False
    try:
        config.random_state = 99
    except Exception:
        raised = True
    assert raised
