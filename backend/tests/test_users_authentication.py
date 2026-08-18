"""Tests for users/authentication.py. Real PostgreSQL throughout."""
import time

import pytest

from users.authentication import (
    AuthenticationService,
    InMemoryEmailVerificationProvider,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from users.config import UsersConfig
from users.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
)
from users.models import DeviceInfo
from users.repository import UsersRepository

_EMAIL_PREFIX = "auth-test"


@pytest.fixture
def repo():
    repository = UsersRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        ids = [row[0] for row in cur.fetchall()]
        if ids:
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_password_reset_tokens WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def provider():
    return InMemoryEmailVerificationProvider()


@pytest.fixture
def service(repo, provider):
    return AuthenticationService(repo, email_provider=provider)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


# ── Password hashing ─────────────────────────────────────────────────────

def test_hash_password_round_trip():
    hashed = hash_password("MyPassw0rd")
    assert verify_password("MyPassw0rd", hashed)
    assert not verify_password("WrongPassword1", hashed)


def test_hash_password_uses_distinct_salts():
    assert hash_password("SamePassw0rd") != hash_password("SamePassw0rd")


def test_verify_password_rejects_malformed_hash():
    assert not verify_password("anything", "not-a-valid-hash")


def test_new_password_hashes_use_the_hardened_default_iteration_count():
    """Production audit LOW batch: PBKDF2 iterations raised from
    260,000 to 600,000 (OWASP's current minimum for PBKDF2-HMAC-SHA256)
    for newly-hashed passwords."""
    hashed = hash_password("MyPassw0rd")
    _, iterations, _, _ = hashed.split("$")
    assert int(iterations) == 600_000
    assert UsersConfig().pbkdf2_iterations == 600_000


def test_an_old_lower_iteration_hash_still_verifies():
    """Backward compatibility: verify_password reads the iteration
    count embedded in the hash string itself, so a password hashed
    under the OLD (260,000) default before this change must keep
    authenticating existing users without a forced rehash/migration."""
    old_config = UsersConfig(pbkdf2_iterations=260_000)
    old_hash = hash_password("MyPassw0rd", old_config)
    assert "$260000$" in old_hash
    assert verify_password("MyPassw0rd", old_hash)
    assert not verify_password("WrongPassword1", old_hash)


def test_hash_password_respects_a_custom_iteration_count():
    custom_config = UsersConfig(pbkdf2_iterations=100_000)
    hashed = hash_password("MyPassw0rd", custom_config)
    assert "$100000$" in hashed
    assert verify_password("MyPassw0rd", hashed)


# ── Opaque tokens ────────────────────────────────────────────────────────

def test_generate_opaque_token_is_unique():
    assert generate_opaque_token() != generate_opaque_token()


def test_hash_token_deterministic():
    token = generate_opaque_token()
    assert hash_token(token) == hash_token(token)


# ── JWT access tokens ────────────────────────────────────────────────────

def test_create_and_decode_access_token():
    token = create_access_token(42)
    assert decode_access_token(token) == 42


def test_decode_access_token_rejects_garbage():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt")


def test_decode_access_token_rejects_wrong_secret():
    config_a = UsersConfig(jwt_secret="secret-a")
    config_b = UsersConfig(jwt_secret="secret-b")
    token = create_access_token(1, config_a)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, config_b)


def test_access_token_expires():
    config = UsersConfig(access_token_expires_seconds=1)
    token = create_access_token(7, config)
    assert decode_access_token(token, config) == 7
    time.sleep(2.5)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, config)


# ── Registration ─────────────────────────────────────────────────────────

def test_register_creates_user_and_sends_verification(service, provider):
    user = service.register(_email("register"), "MyPassw0rd1", "Register Test")
    assert user.id is not None
    assert user.is_email_verified is False
    assert len(provider.sent_verification_emails) == 1
    assert provider.sent_verification_emails[0][0] == _email("register")


def test_register_rejects_duplicate_email(service):
    service.register(_email("dup"), "MyPassw0rd1", "Dup")
    with pytest.raises(EmailAlreadyRegisteredError):
        service.register(_email("dup"), "AnotherPass1", "Dup Again")


def test_register_rejects_invalid_email(service):
    from users.exceptions import ValidationFailedError
    with pytest.raises(ValidationFailedError):
        service.register("not-an-email", "MyPassw0rd1", "Bad Email")


def test_register_rejects_weak_password(service):
    from users.exceptions import ValidationFailedError
    with pytest.raises(ValidationFailedError):
        service.register(_email("weak"), "weak", "Weak Password")


# ── Login / logout ───────────────────────────────────────────────────────

def test_login_success_records_history_and_session(service, repo):
    user = service.register(_email("login"), "MyPassw0rd1", "Login Test")
    device = DeviceInfo(user_agent="pytest-ua", ip_address="9.9.9.9")
    tokens = service.login(_email("login"), "MyPassw0rd1", device)
    assert tokens.access_token and tokens.refresh_token
    assert decode_access_token(tokens.access_token) == user.id

    history = repo.list_login_history(user.id)
    assert len(history) == 1 and history[0].success

    sessions = repo.list_sessions(user.id)
    assert len(sessions) == 1
    assert sessions[0].device.user_agent == "pytest-ua"


def test_login_wrong_password_records_failure(service, repo):
    user = service.register(_email("wrongpw"), "MyPassw0rd1", "Wrong PW")
    with pytest.raises(InvalidCredentialsError):
        service.login(_email("wrongpw"), "WrongPassword1")
    history = repo.list_login_history(user.id)
    assert len(history) == 1 and not history[0].success


def test_login_unknown_email_raises(service):
    with pytest.raises(InvalidCredentialsError):
        service.login(_email("nobody"), "MyPassw0rd1")


def test_login_inactive_account_raises(service, repo):
    user = service.register(_email("inactive"), "MyPassw0rd1", "Inactive")
    user.is_active = False
    repo.update_user(user)
    with pytest.raises(InvalidCredentialsError):
        service.login(_email("inactive"), "MyPassw0rd1")


def test_refresh_rotates_and_revokes_old_token(service):
    service.register(_email("refresh"), "MyPassw0rd1", "Refresh Test")
    tokens = service.login(_email("refresh"), "MyPassw0rd1")
    new_tokens = service.refresh(tokens.refresh_token)
    assert new_tokens.refresh_token != tokens.refresh_token
    with pytest.raises(InvalidTokenError):
        service.refresh(tokens.refresh_token)


def test_refresh_rejects_unknown_token(service):
    with pytest.raises(InvalidTokenError):
        service.refresh("not-a-real-refresh-token")


def test_logout_revokes_session(service):
    service.register(_email("logout"), "MyPassw0rd1", "Logout Test")
    tokens = service.login(_email("logout"), "MyPassw0rd1")
    service.logout(tokens.refresh_token)
    with pytest.raises(InvalidTokenError):
        service.refresh(tokens.refresh_token)


def test_logout_unknown_token_is_a_no_op(service):
    service.logout("not-a-real-refresh-token")  # must not raise


# ── Password reset ───────────────────────────────────────────────────────

def test_password_reset_workflow(service, provider):
    service.register(_email("reset"), "MyPassw0rd1", "Reset Test")
    service.request_password_reset(_email("reset"))
    assert len(provider.sent_password_reset_emails) == 1
    _, token = provider.sent_password_reset_emails[0]

    service.reset_password(token, "NewPassw0rd1")
    tokens = service.login(_email("reset"), "NewPassw0rd1")
    assert tokens.access_token


def test_password_reset_token_is_single_use(service, provider):
    service.register(_email("singleuse"), "MyPassw0rd1", "Single Use")
    service.request_password_reset(_email("singleuse"))
    _, token = provider.sent_password_reset_emails[0]
    service.reset_password(token, "NewPassw0rd1")
    with pytest.raises(InvalidTokenError):
        service.reset_password(token, "AnotherPass1")


def test_password_reset_unknown_email_is_silent(service, provider):
    service.request_password_reset(_email("nonexistent"))
    assert len(provider.sent_password_reset_emails) == 0


def test_reset_password_rejects_invalid_token(service):
    from users.exceptions import ValidationFailedError
    with pytest.raises(InvalidTokenError):
        service.reset_password("garbage-token", "NewPassw0rd1")


# ── Email verification ───────────────────────────────────────────────────

def test_verify_email(service, repo):
    user = service.register(_email("verify"), "MyPassw0rd1", "Verify Test")
    assert repo.get_user(user.id).is_email_verified is False
    service.verify_email(user.id)
    assert repo.get_user(user.id).is_email_verified is True


def test_verify_email_raises_for_unknown_user(service):
    with pytest.raises(UserNotFoundError):
        service.verify_email(999999999)
