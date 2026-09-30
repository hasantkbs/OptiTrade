"""
Regression tests for the production audit's "JWT secret defaults to a
public, known string" Critical finding: `UsersConfig.jwt_secret`
previously defaulted to the literal `"insecure-development-secret-
change-me"` - a string committed to source control - whenever
`USERS_JWT_SECRET` wasn't set, in both `UsersConfig()` (the dataclass
field default) and `UsersConfig.from_env()`. Anyone who has read this
repository (i.e. anyone) could forge a valid access token for any
user_id against a deployment that forgot to set the real secret.

Neither path may ever produce that known string, or any other fixed
literal, again - see users/config.py's `_get_or_generate_ephemeral_jwt_secret`.
"""
import importlib

import pytest

_KNOWN_INSECURE_DEFAULT = "insecure-development-secret-change-me"


@pytest.fixture(autouse=True)
def _reset_ephemeral_secret_cache(monkeypatch):
    """users.config memoizes the generated secret at module level so
    encode/decode stay consistent within one process (see the module's
    own docstring) - reset that cache before/after each test here so
    tests don't leak their generated secret into each other or into the
    rest of the suite."""
    import users.config as users_config

    monkeypatch.setattr(users_config, "_ephemeral_jwt_secret", None)
    yield
    monkeypatch.setattr(users_config, "_ephemeral_jwt_secret", None)


def test_default_construction_never_uses_the_known_insecure_secret(monkeypatch):
    monkeypatch.delenv("USERS_JWT_SECRET", raising=False)
    from users.config import UsersConfig

    config = UsersConfig()
    assert config.jwt_secret != _KNOWN_INSECURE_DEFAULT
    assert len(config.jwt_secret) >= 32


def test_from_env_never_uses_the_known_insecure_secret_when_unset(monkeypatch):
    monkeypatch.delenv("USERS_JWT_SECRET", raising=False)
    from users.config import UsersConfig

    config = UsersConfig.from_env()
    assert config.jwt_secret != _KNOWN_INSECURE_DEFAULT
    assert len(config.jwt_secret) >= 32


def test_from_env_respects_an_explicitly_configured_secret(monkeypatch):
    monkeypatch.setenv("USERS_JWT_SECRET", "a-real-production-secret")
    from users.config import UsersConfig

    config = UsersConfig.from_env()
    assert config.jwt_secret == "a-real-production-secret"


def test_generated_secret_is_stable_within_a_process_but_differs_across_processes(monkeypatch):
    # Stable within a process - create_access_token/decode_access_token
    # each call UsersConfig.from_env() independently (see
    # users/authentication.py) and MUST resolve to the same secret, or
    # a token created moments ago would immediately fail to decode.
    monkeypatch.delenv("USERS_JWT_SECRET", raising=False)
    from users.config import UsersConfig

    first = UsersConfig.from_env()
    second = UsersConfig()
    assert first.jwt_secret == second.jwt_secret

    # Differs across "processes" - simulated here by resetting the
    # module-level cache, since a real second process wouldn't share it.
    import users.config as users_config
    monkeypatch.setattr(users_config, "_ephemeral_jwt_secret", None)
    third = UsersConfig()
    assert third.jwt_secret != first.jwt_secret


def test_tokens_created_and_decoded_in_the_same_process_still_work_with_the_generated_secret(monkeypatch):
    monkeypatch.delenv("USERS_JWT_SECRET", raising=False)
    import users.authentication as auth

    token = auth.create_access_token(4242)
    assert auth.decode_access_token(token) == 4242
