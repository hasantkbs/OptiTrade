"""Tests for engines/technical/config.py."""
from engines.technical.config import (
    ALL_FEATURE_NAMES,
    EMA_CROSSOVER_ENCODING,
    TechnicalEngineConfig,
)


def test_all_feature_names_has_no_duplicates():
    assert len(ALL_FEATURE_NAMES) == len(set(ALL_FEATURE_NAMES))


def test_ema_crossover_encoding_covers_every_calculate_ema_crossover_output():
    # core.indicators.calculate_ema_crossover can return exactly these
    # four strings, or None.
    for value in ("GOLDEN_CROSS", "BULLISH", "BEARISH", "DEATH_CROSS", None):
        assert value in EMA_CROSSOVER_ENCODING


def test_config_from_env_defaults(monkeypatch):
    for key in (
        "TECHNICAL_ENGINE_PRICE_PERIOD", "TECHNICAL_ENGINE_MAX_FEATURE_AGE_SECONDS",
        "TECHNICAL_ENGINE_DECISION_THRESHOLD", "TECHNICAL_ENGINE_EXPECTED_RETURN_SCALE",
        "TECHNICAL_ENGINE_VOLUME_AVERAGE_WINDOW", "TECHNICAL_ENGINE_SUPPORT_RESISTANCE_LOOKBACK_DAYS",
        "TECHNICAL_ENGINE_VERSION",
    ):
        monkeypatch.delenv(key, raising=False)

    config = TechnicalEngineConfig.from_env()
    assert config.price_period == "6mo"
    assert config.max_feature_age_seconds == 3600
    assert config.decision_threshold == 0.2
    assert config.expected_return_scale == 1.0
    assert config.volume_average_window == 20
    assert config.support_resistance_lookback_days == 30
    assert config.engine_version == "v1"


def test_config_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("TECHNICAL_ENGINE_PRICE_PERIOD", "1y")
    monkeypatch.setenv("TECHNICAL_ENGINE_DECISION_THRESHOLD", "0.3")
    monkeypatch.setenv("TECHNICAL_ENGINE_VERSION", "v2")

    config = TechnicalEngineConfig.from_env()
    assert config.price_period == "1y"
    assert config.decision_threshold == 0.3
    assert config.engine_version == "v2"


def test_config_is_frozen():
    config = TechnicalEngineConfig()
    try:
        config.decision_threshold = 0.9  # type: ignore[misc]
        assert False, "expected an error assigning to a frozen dataclass"
    except AttributeError:
        pass
