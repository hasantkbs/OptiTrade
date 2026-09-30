"""Tests for research_lab/config.py."""
from research_lab.config import ResearchLabConfig


def test_default_config_values():
    config = ResearchLabConfig()
    assert config.walk_forward_train_window_days == 90
    assert config.significance_level == 0.05
    assert config.promotion_margin == 0.03


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("RESEARCH_LAB_PROMOTION_MARGIN", "0.1")
    monkeypatch.setenv("RESEARCH_LAB_SIGNIFICANCE_LEVEL", "0.01")
    config = ResearchLabConfig.from_env()
    assert config.promotion_margin == 0.1
    assert config.significance_level == 0.01


def test_from_env_defaults_when_unset(monkeypatch):
    for var in ["RESEARCH_LAB_PROMOTION_MARGIN", "RESEARCH_LAB_SIGNIFICANCE_LEVEL"]:
        monkeypatch.delenv(var, raising=False)
    config = ResearchLabConfig.from_env()
    assert config.promotion_margin == 0.03
    assert config.significance_level == 0.05


def test_config_is_frozen():
    config = ResearchLabConfig()
    raised = False
    try:
        config.promotion_margin = 0.5
    except Exception:
        raised = True
    assert raised
