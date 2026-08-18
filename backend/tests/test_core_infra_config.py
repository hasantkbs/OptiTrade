"""
Tests for core/infra_config.py (production audit LOW batch: "duplicated
Redis/Postgres configuration fallback logic"). Every package's own
Config.from_env() previously re-implemented the identical
PACKAGE_REDIS_* -> FEATURE_STORE_REDIS_* -> hardcoded-default chain
inline; this module centralizes it. These tests lock down the exact
precedence every existing caller depends on.
"""
import pytest

from core.infra_config import (
    postgres_settings_from_env,
    redis_settings_from_env,
    redis_socket_timeout_seconds,
)


def test_redis_settings_default_to_localhost_when_nothing_is_set(monkeypatch):
    for var in ("FOO_REDIS_HOST", "FOO_REDIS_PORT", "FOO_REDIS_DB", "FEATURE_STORE_REDIS_HOST",
                "FEATURE_STORE_REDIS_PORT", "FEATURE_STORE_REDIS_DB"):
        monkeypatch.delenv(var, raising=False)
    assert redis_settings_from_env("FOO") == ("localhost", 6379, 0)


def test_redis_settings_falls_back_to_the_shared_feature_store_settings(monkeypatch):
    monkeypatch.delenv("FOO_REDIS_HOST", raising=False)
    monkeypatch.delenv("FOO_REDIS_PORT", raising=False)
    monkeypatch.delenv("FOO_REDIS_DB", raising=False)
    monkeypatch.setenv("FEATURE_STORE_REDIS_HOST", "shared-redis")
    monkeypatch.setenv("FEATURE_STORE_REDIS_PORT", "6380")
    monkeypatch.setenv("FEATURE_STORE_REDIS_DB", "3")
    assert redis_settings_from_env("FOO") == ("shared-redis", 6380, 3)


def test_redis_settings_package_specific_override_wins(monkeypatch):
    monkeypatch.setenv("FEATURE_STORE_REDIS_HOST", "shared-redis")
    monkeypatch.setenv("FOO_REDIS_HOST", "foo-only-redis")
    monkeypatch.setenv("FOO_REDIS_PORT", "7000")
    monkeypatch.setenv("FOO_REDIS_DB", "9")
    assert redis_settings_from_env("FOO") == ("foo-only-redis", 7000, 9)


def test_postgres_settings_default_when_nothing_is_set(monkeypatch):
    for var in ("FEATURE_STORE_POSTGRES_HOST", "FEATURE_STORE_POSTGRES_PORT", "FEATURE_STORE_POSTGRES_DB",
                "FEATURE_STORE_POSTGRES_USER", "FEATURE_STORE_POSTGRES_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    assert postgres_settings_from_env() == ("localhost", 5432, "optitrade", "optitrade_user", "")


def test_postgres_settings_reads_the_shared_feature_store_env_vars(monkeypatch):
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_HOST", "pg-host")
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_PORT", "5433")
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_DB", "mydb")
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_USER", "myuser")
    monkeypatch.setenv("FEATURE_STORE_POSTGRES_PASSWORD", "mypass")
    assert postgres_settings_from_env() == ("pg-host", 5433, "mydb", "myuser", "mypass")


def test_redis_socket_timeout_defaults_to_five_seconds(monkeypatch):
    monkeypatch.delenv("REDIS_SOCKET_TIMEOUT_SECONDS", raising=False)
    assert redis_socket_timeout_seconds() == pytest.approx(5.0)


def test_redis_socket_timeout_is_configurable(monkeypatch):
    monkeypatch.setenv("REDIS_SOCKET_TIMEOUT_SECONDS", "2.5")
    assert redis_socket_timeout_seconds() == pytest.approx(2.5)
