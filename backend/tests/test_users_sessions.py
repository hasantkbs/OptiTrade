"""Tests for users/sessions.py. Real PostgreSQL + real Redis (an isolated
logical DB, matching `tests/test_feature_store_online_store.py`'s own
convention)."""
from datetime import datetime, timedelta, timezone

import pytest
import redis

from users.authentication import generate_opaque_token, hash_token
from users.config import UsersConfig
from users.models import DeviceInfo, Session, User
from users.repository import UsersRepository
from users.sessions import SessionService

_EMAIL_PREFIX = "sessions-test"


@pytest.fixture
def redis_client():
    client = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def repo():
    repository = UsersRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        ids = [row[0] for row in cur.fetchall()]
        if ids:
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def config():
    return UsersConfig(redis_db=15, session_cache_ttl_seconds=300)


@pytest.fixture
def service(repo, config, redis_client):
    return SessionService(repo, config=config, client=redis_client)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _make_session(repo, user_id, refresh_token, expires_in_seconds=3600):
    return repo.save_session(
        Session(
            user_id=user_id, refresh_token_hash=hash_token(refresh_token), device=DeviceInfo(user_agent="ua"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds),
        )
    )


def test_get_active_session_falls_back_to_repository_on_cache_miss(repo, service):
    user_id = repo.save_user(User(email=_email("miss"), password_hash="h", display_name="Miss Test"))
    token = generate_opaque_token()
    _make_session(repo, user_id, token)

    session = service.get_active_session(token)
    assert session is not None
    assert session.user_id == user_id


def test_get_active_session_uses_cache_on_second_call(repo, service, redis_client):
    user_id = repo.save_user(User(email=_email("cache"), password_hash="h", display_name="Cache Test"))
    token = generate_opaque_token()
    _make_session(repo, user_id, token)

    first = service.get_active_session(token)
    assert first is not None
    # Delete from Postgres directly - if the second call still succeeds,
    # it must have been served from the Redis cache, not the database.
    with repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users_sessions WHERE user_id = %s", (user_id,))
    second = service.get_active_session(token)
    assert second is not None
    assert second.user_id == user_id


def test_get_active_session_returns_none_for_unknown_token(service):
    assert service.get_active_session("not-a-real-token") is None


def test_get_active_session_returns_none_for_revoked_session(repo, service):
    user_id = repo.save_user(User(email=_email("revoked"), password_hash="h", display_name="Revoked Test"))
    token = generate_opaque_token()
    session_id = _make_session(repo, user_id, token)
    session = repo.get_session(session_id)
    session.revoked_at = datetime.now(timezone.utc)
    repo.update_session(session)

    assert service.get_active_session(token) is None


def test_get_active_session_returns_none_for_expired_session(repo, service):
    user_id = repo.save_user(User(email=_email("expired"), password_hash="h", display_name="Expired Test"))
    token = generate_opaque_token()
    _make_session(repo, user_id, token, expires_in_seconds=-3600)

    assert service.get_active_session(token) is None


def test_invalidate_removes_cache_entry(repo, service):
    user_id = repo.save_user(User(email=_email("invalidate"), password_hash="h", display_name="Invalidate Test"))
    token = generate_opaque_token()
    _make_session(repo, user_id, token)

    assert service.get_active_session(token) is not None
    service.invalidate(token)
    # Revoke in Postgres too - invalidate() only clears the cache, so a
    # still-active DB row would otherwise mask whether the cache was
    # really cleared (get_active_session falls back to the repository).
    with repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users_sessions WHERE user_id = %s", (user_id,))
    assert service.get_active_session(token) is None


def test_list_active_sessions_excludes_revoked(repo, service):
    user_id = repo.save_user(User(email=_email("listactive"), password_hash="h", display_name="List Active"))
    _make_session(repo, user_id, generate_opaque_token())
    revoked_id = _make_session(repo, user_id, generate_opaque_token())
    revoked = repo.get_session(revoked_id)
    revoked.revoked_at = datetime.now(timezone.utc)
    repo.update_session(revoked)

    active = service.list_active_sessions(user_id)
    assert len(active) == 1


def test_get_cached_survives_redis_error(repo, config):
    class _BrokenRedis:
        def get(self, key):
            raise redis.RedisError("boom")

        def set(self, *args, **kwargs):
            raise redis.RedisError("boom")

        def delete(self, key):
            raise redis.RedisError("boom")

    service = SessionService(repo, config=config, client=_BrokenRedis())
    user_id = repo.save_user(User(email=_email("brokenredis"), password_hash="h", display_name="Broken Redis"))
    token = generate_opaque_token()
    _make_session(repo, user_id, token)

    # Redis is broken, but the repository fallback must still work.
    session = service.get_active_session(token)
    assert session is not None
    with repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users_sessions WHERE user_id = %s", (user_id,))
