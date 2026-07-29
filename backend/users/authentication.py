"""
OptiTrade User & Organization Platform — authentication.

Password hashing: PBKDF2-HMAC-SHA256 (stdlib `hashlib`, NIST-approved,
zero new dependency) with a random salt and constant-time verification.

Tokens: a stateless JWT access token (short-lived, signed with
`python-jose`) plus an opaque, server-side-revocable refresh token
(`Session.refresh_token_hash` - only the SHA-256 hash is ever persisted,
the plaintext refresh token is returned to the caller exactly once).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List, Optional, Protocol, Tuple

from jose import JWTError, jwt

if TYPE_CHECKING:
    from users.sessions import SessionService

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from users.config import UsersConfig
from users.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
)
from users.models import DeviceInfo, LoginHistoryEntry, PasswordResetToken, Session, TokenPair, User
from users.repository import UsersRepository
from users.validators import validate_email_format, validate_password_strength

logger = logging.getLogger(__name__)
_MODULE = "users.authentication"
_COMPONENT = "users"


# ── Password hashing ─────────────────────────────────────────────────────

def hash_password(password: str, config: Optional[UsersConfig] = None) -> str:
    config = config or UsersConfig.from_env()
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, config.pbkdf2_iterations)
    return f"pbkdf2_sha256${config.pbkdf2_iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_str, salt_hex, hash_hex = password_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_str))
    return hmac.compare_digest(derived, expected)


# ── Opaque secret tokens (refresh tokens, password reset tokens,
# invitation tokens all use this same primitive) ─────────────────────────

def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── JWT access tokens ─────────────────────────────────────────────────────

def create_access_token(user_id: int, config: Optional[UsersConfig] = None) -> str:
    config = config or UsersConfig.from_env()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=config.access_token_expires_seconds),
        "type": "access",
    }
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)


def decode_access_token(token: str, config: Optional[UsersConfig] = None) -> int:
    config = config or UsersConfig.from_env()
    try:
        payload = jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError(f"invalid access token: {exc}") from exc
    if payload.get("type") != "access":
        raise InvalidTokenError("not an access token")
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("malformed access token payload") from exc


# ── Email verification provider abstraction — interface only. No real
# email delivery is in scope; the default in-memory provider simply
# records what would have been sent. ─────────────────────────────────────

class EmailVerificationProvider(Protocol):
    def send_verification_email(self, email: str, token: str) -> None: ...
    def send_password_reset_email(self, email: str, token: str) -> None: ...


class InMemoryEmailVerificationProvider:
    def __init__(self) -> None:
        self.sent_verification_emails: List[Tuple[str, str]] = []
        self.sent_password_reset_emails: List[Tuple[str, str]] = []

    def send_verification_email(self, email: str, token: str) -> None:
        self.sent_verification_emails.append((email, token))

    def send_password_reset_email(self, email: str, token: str) -> None:
        self.sent_password_reset_emails.append((email, token))


class AuthenticationService:
    """Registration, login/logout, refresh-token rotation, login history,
    device tracking, and the password reset workflow."""

    def __init__(
        self,
        repository: UsersRepository,
        config: Optional[UsersConfig] = None,
        email_provider: Optional[EmailVerificationProvider] = None,
        session_cache: Optional["SessionService"] = None,
    ) -> None:
        self._repository = repository
        self._config = config or UsersConfig.from_env()
        self._email_provider = email_provider or InMemoryEmailVerificationProvider()
        self._session_cache = session_cache

    def register(self, email: str, password: str, display_name: str) -> User:
        started_at = time.perf_counter()
        validate_email_format(email)
        validate_password_strength(password)
        if self._repository.get_user_by_email(email) is not None:
            self._log_error("register", EmailAlreadyRegisteredError(), started_at, email=email)
            raise EmailAlreadyRegisteredError(f"{email} is already registered")

        user = User(email=email, password_hash=hash_password(password, self._config), display_name=display_name)
        user_id = self._repository.save_user(user)
        user = self._repository.get_user(user_id)
        self._email_provider.send_verification_email(user.email, generate_opaque_token())
        self._log_success("register", started_at, user_id=user_id)
        return user

    def login(self, email: str, password: str, device: Optional[DeviceInfo] = None) -> TokenPair:
        started_at = time.perf_counter()
        device = device or DeviceInfo()
        user = self._repository.get_user_by_email(email)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            self._repository.save_login_history(
                LoginHistoryEntry(
                    user_id=user.id if user else None,
                    email=email.strip().lower(),
                    success=False,
                    failure_reason="account_inactive" if user and not user.is_active else "invalid_credentials",
                    device=device,
                )
            )
            self._log_error("login", InvalidCredentialsError(), started_at, email=email)
            raise InvalidCredentialsError("invalid email or password")

        token_pair = self._issue_token_pair(user, device)
        user.last_login_at = datetime.now(timezone.utc)
        self._repository.update_user(user)
        self._repository.save_login_history(
            LoginHistoryEntry(user_id=user.id, email=user.email, success=True, device=device)
        )
        self._log_success("login", started_at, user_id=user.id)
        return token_pair

    def refresh(self, refresh_token: str, device: Optional[DeviceInfo] = None) -> TokenPair:
        started_at = time.perf_counter()
        session = self._repository.get_session_by_token_hash(hash_token(refresh_token))
        now = datetime.now(timezone.utc)
        if session is None or session.revoked_at is not None or session.expires_at < now:
            self._log_error("refresh", InvalidTokenError(), started_at)
            raise InvalidTokenError("invalid, expired, or revoked refresh token")

        user = self._repository.get_user(session.user_id)
        if user is None or not user.is_active:
            self._log_error("refresh", InvalidTokenError(), started_at)
            raise InvalidTokenError("invalid, expired, or revoked refresh token")

        session.revoked_at = now
        session.last_used_at = now
        self._repository.update_session(session)
        if self._session_cache is not None:
            self._session_cache.invalidate(refresh_token)
        token_pair = self._issue_token_pair(user, device or session.device)
        self._log_success("refresh", started_at, user_id=user.id)
        return token_pair

    def logout(self, refresh_token: str) -> None:
        started_at = time.perf_counter()
        session = self._repository.get_session_by_token_hash(hash_token(refresh_token))
        if session is None:
            self._log_success("logout", started_at, found=False)
            return
        session.revoked_at = datetime.now(timezone.utc)
        self._repository.update_session(session)
        if self._session_cache is not None:
            self._session_cache.invalidate(refresh_token)
        self._log_success("logout", started_at, user_id=session.user_id, found=True)

    def request_password_reset(self, email: str) -> None:
        started_at = time.perf_counter()
        user = self._repository.get_user_by_email(email)
        if user is None:
            # Deliberately silent about whether the account exists.
            self._log_success("request_password_reset", started_at, found=False)
            return
        token = generate_opaque_token()
        self._repository.save_password_reset_token(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=now_plus(self._config.password_reset_token_expires_seconds),
            )
        )
        self._email_provider.send_password_reset_email(user.email, token)
        self._log_success("request_password_reset", started_at, user_id=user.id, found=True)

    def reset_password(self, token: str, new_password: str) -> None:
        started_at = time.perf_counter()
        validate_password_strength(new_password)
        reset_token = self._repository.get_password_reset_token_by_hash(hash_token(token))
        now = datetime.now(timezone.utc)
        if reset_token is None or reset_token.used_at is not None or reset_token.expires_at < now:
            self._log_error("reset_password", InvalidTokenError(), started_at)
            raise InvalidTokenError("invalid, expired, or already-used password reset token")

        user = self._repository.get_user(reset_token.user_id)
        if user is None:
            raise UserNotFoundError(f"user {reset_token.user_id} not found")
        user.password_hash = hash_password(new_password, self._config)
        self._repository.update_user(user)
        self._repository.mark_password_reset_token_used(reset_token.id, now)
        self._log_success("reset_password", started_at, user_id=user.id)

    def verify_email(self, user_id: int) -> None:
        user = self._repository.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"user {user_id} not found")
        user.is_email_verified = True
        self._repository.update_user(user)

    def _issue_token_pair(self, user: User, device: DeviceInfo) -> TokenPair:
        access_token = create_access_token(user.id, self._config)
        refresh_token = generate_opaque_token()
        self._repository.save_session(
            Session(
                user_id=user.id,
                refresh_token_hash=hash_token(refresh_token),
                device=device,
                expires_at=now_plus(self._config.refresh_token_expires_seconds),
            )
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._config.access_token_expires_seconds,
        )

    def _log_success(self, operation: str, started_at: float, **extra) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, **extra,
        )

    def _log_error(self, operation: str, exc: Exception, started_at: float, **extra) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_ERROR,
            error_type=type(exc).__name__, execution_time_ms=(time.perf_counter() - started_at) * 1000,
            level=logging.ERROR, **extra,
        )


def now_plus(seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
