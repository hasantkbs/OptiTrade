"""Tests for feature_store/config.py and feature_store/exceptions.py."""
from feature_store.config import FeatureStoreConfig
from feature_store.exceptions import FeatureNotFoundError, FeatureStoreError, FeatureValidationError


def test_from_env_reads_the_configured_test_environment(monkeypatch):
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_HOST", "pg.example.com")
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_PORT", "5433")
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_DB", "mydb")
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_USER", "myuser")
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_PASSWORD", "mypass")
    monkeypatch.setenv("FEATURE_STORE_REDIS_HOST", "redis.example.com")
    monkeypatch.setenv("FEATURE_STORE_REDIS_PORT", "6380")
    monkeypatch.setenv("FEATURE_STORE_REDIS_DB", "2")
    monkeypatch.setenv("FEATURE_STORE_ONLINE_TTL_SECONDS", "120")

    config = FeatureStoreConfig.from_env()

    assert config.postgres_host == "pg.example.com"
    assert config.postgres_port == 5433
    assert config.postgres_db == "mydb"
    assert config.postgres_user == "myuser"
    assert config.postgres_password == "mypass"
    assert config.redis_host == "redis.example.com"
    assert config.redis_port == 6380
    assert config.redis_db == 2
    assert config.online_ttl_seconds == 120


def test_from_env_defaults_when_unset(monkeypatch):
    for key in (
        "FEATURE_STORE_POSTGRES_HOST", "FEATURE_STORE_POSTGRES_PORT",
        "FEATURE_STORE_POSTGRES_DB", "FEATURE_STORE_POSTGRES_USER",
        "FEATURE_STORE_POSTGRES_PASSWORD", "FEATURE_STORE_REDIS_HOST",
        "FEATURE_STORE_REDIS_PORT", "FEATURE_STORE_REDIS_DB",
        "FEATURE_STORE_ONLINE_TTL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    config = FeatureStoreConfig.from_env()

    assert config.postgres_host == "localhost"
    assert config.postgres_port == 5432
    assert config.postgres_db == "optitrade"
    assert config.postgres_user == "optitrade_user"
    assert config.redis_host == "localhost"
    assert config.redis_port == 6379
    assert config.redis_db == 0
    assert config.online_ttl_seconds == 900


def test_config_is_frozen():
    config = FeatureStoreConfig(
        postgres_host="h", postgres_port=1, postgres_db="d", postgres_user="u",
        postgres_password="p", redis_host="h2", redis_port=2, redis_db=0,
    )
    try:
        config.postgres_host = "changed"  # type: ignore[misc]
        assert False, "expected an error assigning to a frozen dataclass"
    except AttributeError:
        pass


def test_feature_validation_error_message_includes_symbol_and_errors():
    exc = FeatureValidationError("BTC-USD", "rsi_14", ["value is NaN"])
    assert exc.symbol == "BTC-USD"
    assert exc.feature_name == "rsi_14"
    assert "rsi_14" in str(exc)
    assert "BTC-USD" in str(exc)
    assert "value is NaN" in str(exc)
    assert isinstance(exc, FeatureStoreError)


def test_feature_not_found_error_message():
    exc = FeatureNotFoundError("BTC-USD", "rsi_14")
    assert exc.symbol == "BTC-USD"
    assert exc.feature_name == "rsi_14"
    assert isinstance(exc, FeatureStoreError)
