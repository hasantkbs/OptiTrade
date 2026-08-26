"""Tests for engines/news/config.py."""
from engines.news.config import ALL_FEATURE_NAMES, NewsEngineConfig


def test_all_feature_names_has_five_entries():
    assert len(ALL_FEATURE_NAMES) == 5
    assert len(set(ALL_FEATURE_NAMES)) == 5


def test_default_config_values():
    config = NewsEngineConfig()
    assert config.max_articles == 15
    assert config.max_age_days == 7
    assert config.decision_threshold == 0.2
    assert config.engine_version == "v1"


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("NEWS_ENGINE_MAX_ARTICLES", "25")
    monkeypatch.setenv("NEWS_ENGINE_DECISION_THRESHOLD", "0.3")
    monkeypatch.setenv("NEWS_ENGINE_VERSION", "v2")
    config = NewsEngineConfig.from_env()
    assert config.max_articles == 25
    assert config.decision_threshold == 0.3
    assert config.engine_version == "v2"


def test_from_env_defaults_when_unset(monkeypatch):
    for var in [
        "NEWS_ENGINE_MAX_ARTICLES", "NEWS_ENGINE_MAX_AGE_DAYS", "NEWS_ENGINE_DECISION_THRESHOLD",
        "NEWS_ENGINE_EXPECTED_RETURN_SCALE_PCT", "NEWS_ENGINE_VERSION",
    ]:
        monkeypatch.delenv(var, raising=False)
    config = NewsEngineConfig.from_env()
    assert config.max_articles == 15
    assert config.engine_version == "v1"


def test_config_is_frozen():
    config = NewsEngineConfig()
    try:
        config.max_articles = 99
        assert False, "should have raised"
    except Exception:
        pass
