"""
Regression tests for core/infra_config.py's PostgreSQL advisory locks
(SERVER STEP 4): schema_init_lock(), and its key separation from the
pre-existing acquire_scheduler_leader_lock()/release_scheduler_leader_lock()
(SERVER STEP 1).

Deterministic - a fake psycopg2.connect() records every SQL statement
executed against it instead of touching a real database, so these
tests exercise schema_init_lock()'s actual locking/release/error-
propagation logic without depending on real PostgreSQL concurrency
(which would be flaky by nature). The real multi-worker race this lock
prevents is verified live against a real, fresh PostgreSQL database in
SERVER STEP 4's Docker Compose verification - these tests cover the
deterministic contract only.
"""
import pytest

from core.infra_config import (
    _SCHEDULER_LEADER_LOCK_KEY,
    _SCHEMA_INIT_LOCK_KEY,
    schema_init_lock,
)


class _FakeCursor:
    def __init__(self, calls):
        self._calls = calls

    def execute(self, sql, params=None):
        self._calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return (True,)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeConnection:
    def __init__(self, calls):
        self._calls = calls
        self.autocommit = False
        self.closed = False

    def cursor(self):
        return _FakeCursor(self._calls)

    def close(self):
        self.closed = True


def test_schema_init_lock_key_is_distinct_from_scheduler_leader_lock_key():
    """The two locks answer unrelated questions and must never collide -
    see schema_init_lock()'s own docstring for why sharing a key would
    be actively harmful, not just redundant."""
    assert _SCHEMA_INIT_LOCK_KEY != _SCHEDULER_LEADER_LOCK_KEY


def test_schema_init_lock_acquires_the_dedicated_advisory_lock_key(monkeypatch):
    calls = []
    monkeypatch.setattr("psycopg2.connect", lambda **kw: _FakeConnection(calls))

    with schema_init_lock():
        pass

    lock_calls = [c for c in calls if c[0] == "SELECT pg_advisory_lock(%s)"]
    assert len(lock_calls) == 1
    assert lock_calls[0][1] == (_SCHEMA_INIT_LOCK_KEY,)


def test_schema_init_lock_uses_the_blocking_lock_not_try_lock(monkeypatch):
    """Blocking (not pg_try_advisory_lock) is the actual mechanism that
    makes two concurrent callers unable to both proceed at once - a
    second caller's `pg_advisory_lock` call simply waits at the
    PostgreSQL level until the first releases, rather than racing."""
    calls = []
    monkeypatch.setattr("psycopg2.connect", lambda **kw: _FakeConnection(calls))

    with schema_init_lock():
        pass

    sql_statements = [c[0] for c in calls]
    assert "SELECT pg_advisory_lock(%s)" in sql_statements
    assert not any("pg_try_advisory_lock" in sql for sql in sql_statements)


def test_schema_init_lock_releases_and_closes_after_successful_use(monkeypatch):
    calls = []
    fake_conn = _FakeConnection(calls)
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)

    with schema_init_lock():
        pass

    unlock_calls = [c for c in calls if c[0] == "SELECT pg_advisory_unlock(%s)"]
    assert len(unlock_calls) == 1
    assert unlock_calls[0][1] == (_SCHEMA_INIT_LOCK_KEY,)
    assert fake_conn.closed is True


def test_schema_init_lock_releases_and_reraises_on_failure(monkeypatch):
    """Item C: a real schema-initialization error must propagate, never
    be swallowed just because the lock needs releasing."""
    calls = []
    fake_conn = _FakeConnection(calls)
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)

    class _SimulatedSchemaError(Exception):
        pass

    with pytest.raises(_SimulatedSchemaError, match="simulated CREATE TABLE failure"):
        with schema_init_lock():
            raise _SimulatedSchemaError("simulated CREATE TABLE failure")

    unlock_calls = [c for c in calls if c[0] == "SELECT pg_advisory_unlock(%s)"]
    assert len(unlock_calls) == 1
    assert fake_conn.closed is True


def test_schema_init_lock_fails_open_when_postgres_is_unreachable(monkeypatch):
    """Matches acquire_scheduler_leader_lock's existing fail-open
    convention: every repository construction inside the `with` block
    needs the same PostgreSQL connection and will fail identically and
    visibly through its own existing error handling regardless of
    whether this lock was held, so proceeding unserialized here can't
    introduce a race that wasn't already impossible to avoid."""
    def _raise_connect(**kw):
        raise OSError("simulated: connection refused")

    monkeypatch.setattr("psycopg2.connect", _raise_connect)

    entered = []
    with schema_init_lock():
        entered.append(True)

    assert entered == [True]


def test_schema_init_lock_can_be_acquired_and_released_repeatedly(monkeypatch):
    """An already-initialized database (a second/later startup) must
    keep working: the lock is not a one-shot resource."""
    calls = []
    connections = []

    def _fake_connect(**kw):
        conn = _FakeConnection(calls)
        connections.append(conn)
        return conn

    monkeypatch.setattr("psycopg2.connect", _fake_connect)

    with schema_init_lock():
        pass
    with schema_init_lock():
        pass

    assert len(connections) == 2
    assert all(conn.closed for conn in connections)
    lock_calls = [c for c in calls if c[0] == "SELECT pg_advisory_lock(%s)"]
    unlock_calls = [c for c in calls if c[0] == "SELECT pg_advisory_unlock(%s)"]
    assert len(lock_calls) == 2
    assert len(unlock_calls) == 2
