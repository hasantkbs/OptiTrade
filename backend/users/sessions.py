"""
OptiTrade User & Organization Platform — Redis session cache.

A thin, fast-path cache in front of `UsersRepository`'s Postgres-backed
`users_sessions` table, so that validating a refresh token/session on
every request doesn't require a database round trip. Cache entries are
looked up by the SHA-256 hash of the refresh token (never the plaintext),
matching how the token is stored in Postgres.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import redis

from core.structured_logging import STATUS_ERROR, log_event
from users.config import UsersConfig
from users.models import Session
from users.repository import UsersRepository

logger = logging.getLogger(__name__)
_MODULE = "users.sessions"
_COMPONENT = "users"
_KEY_PREFIX = "users:session"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionService:
    def __init__(
        self,
        repository: UsersRepository,
        config: Optional[UsersConfig] = None,
        client: Optional["redis.Redis"] = None,
    ) -> None:
        self._repository = repository
        self._config = config or UsersConfig.from_env()
        self._client = client or redis.Redis(
            host=self._config.redis_host, port=self._config.redis_port,
            db=self._config.redis_db, decode_responses=True,
        )

    def get_active_session(self, refresh_token: str) -> Optional[Session]:
        token_hash = _hash_token(refresh_token)
        session = self._get_cached(token_hash)
        if session is None:
            session = self._repository.get_session_by_token_hash(token_hash)
            if session is None:
                return None
            self._set_cached(token_hash, session)
        return session if self._is_active(session) else None

    def invalidate(self, refresh_token: str) -> None:
        self._delete_cached(_hash_token(refresh_token))

    def list_active_sessions(self, user_id: int) -> list:
        return [session for session in self._repository.list_sessions(user_id) if self._is_active(session)]

    @staticmethod
    def _is_active(session: Session) -> bool:
        return session.revoked_at is None and session.expires_at > datetime.now(timezone.utc)

    def _get_cached(self, token_hash: str) -> Optional[Session]:
        try:
            raw = self._client.get(f"{_KEY_PREFIX}:{token_hash}")
        except redis.RedisError as exc:
            self._log_warning("get_cached", exc)
            return None
        if raw is None:
            return None
        try:
            return Session.model_validate_json(raw)
        except Exception:
            return None

    def _set_cached(self, token_hash: str, session: Session) -> None:
        try:
            self._client.set(
                f"{_KEY_PREFIX}:{token_hash}", session.model_dump_json(),
                ex=self._config.session_cache_ttl_seconds,
            )
        except redis.RedisError as exc:
            self._log_warning("set_cached", exc)

    def _delete_cached(self, token_hash: str) -> None:
        try:
            self._client.delete(f"{_KEY_PREFIX}:{token_hash}")
        except redis.RedisError as exc:
            self._log_warning("delete_cached", exc)

    def _log_warning(self, operation: str, exc: Exception) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_ERROR,
            error_type=type(exc).__name__, level=logging.WARNING,
        )
