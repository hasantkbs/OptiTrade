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

import core.infra_config as infra_config
from core.infra_config import (
    _SCHEDULER_LEADER_LOCK_KEY,
    _SCHEMA_INIT_LOCK_KEY,
    acquire_scheduler_leader_lock,
    release_scheduler_leader_lock,
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


# ── acquire_scheduler_leader_lock() / release_scheduler_leader_lock() ──────
#
# Task 0.2-F (CTO Remediation Plan Revision 4, Finding A9 / Section 6.4):
# dedicated, direct tests for the scheduler leader lock itself - previously
# only exercised indirectly (a comment noting it shares schema_init_lock's
# fail-open convention, and a source-text-scan test elsewhere checking only
# that main.py's startup code *calls* this function, never its own
# behavior). These tests characterize the function exactly as implemented
# today - see the module-level docstring's own description of its fail-open
# contract - not an idealized/assumed one; `_FakeAdvisoryCursor`'s
# `raise_on_execute` exists specifically to reach the "connect() succeeded,
# a later step failed" branch, distinct from "connect() itself failed".


class _FakeAdvisoryCursor:
    def __init__(self, calls, fetchone_result=(True,), raise_on_execute=None):
        self._calls = calls
        self._fetchone_result = fetchone_result
        self._raise_on_execute = raise_on_execute

    def execute(self, sql, params=None):
        if self._raise_on_execute is not None:
            raise self._raise_on_execute
        self._calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self._fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeAdvisoryConnection:
    def __init__(self, calls, fetchone_result=(True,), raise_on_execute=None, raise_on_close=None):
        self._calls = calls
        self._fetchone_result = fetchone_result
        self._raise_on_execute = raise_on_execute
        self._raise_on_close = raise_on_close
        self.autocommit = False
        self.closed = False

    def cursor(self):
        return _FakeAdvisoryCursor(self._calls, self._fetchone_result, self._raise_on_execute)

    def close(self):
        if self._raise_on_close is not None:
            raise self._raise_on_close
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_scheduler_leader_lock_global(monkeypatch):
    """Isolates every test in this section from the real module-global
    `_scheduler_leader_lock_conn` - acquire_scheduler_leader_lock()/
    release_scheduler_leader_lock() mutate it directly (it is not an
    injectable dependency), so without this, one test's acquired "lock"
    would leak into the next test's starting state."""
    monkeypatch.setattr(infra_config, "_scheduler_leader_lock_conn", None)


def test_acquire_scheduler_leader_lock_succeeds_and_holds_connection_open(monkeypatch):
    """Requirement 1 (successful acquisition): pg_try_advisory_lock
    returning true means this worker won - the function returns True,
    sets autocommit (required for an advisory lock taken outside an
    explicit transaction), and deliberately keeps the connection open
    (never calls close()) for as long as this process holds the lock."""
    calls = []
    fake_conn = _FakeAdvisoryConnection(calls, fetchone_result=(True,))
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)

    result = acquire_scheduler_leader_lock()

    assert result is True
    assert fake_conn.autocommit is True
    assert fake_conn.closed is False
    lock_calls = [c for c in calls if c[0] == "SELECT pg_try_advisory_lock(%s)"]
    assert len(lock_calls) == 1
    assert lock_calls[0][1] == (_SCHEDULER_LEADER_LOCK_KEY,)
    assert infra_config._scheduler_leader_lock_conn is fake_conn


def test_acquire_scheduler_leader_lock_uses_the_non_blocking_try_lock_not_blocking_lock(monkeypatch):
    """Mirrors schema_init_lock's own symmetric test: this lock must
    never block a worker - a loser moves on immediately rather than
    waiting for the leader to release."""
    calls = []
    fake_conn = _FakeAdvisoryConnection(calls, fetchone_result=(True,))
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)

    acquire_scheduler_leader_lock()

    sql_statements = [c[0] for c in calls]
    assert any("pg_try_advisory_lock" in sql for sql in sql_statements)
    assert not any(sql == "SELECT pg_advisory_lock(%s)" for sql in sql_statements)


def test_acquire_scheduler_leader_lock_uses_its_own_key_not_the_schema_init_key(monkeypatch):
    calls = []
    fake_conn = _FakeAdvisoryConnection(calls, fetchone_result=(True,))
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)

    acquire_scheduler_leader_lock()

    assert calls[0][1] == (_SCHEDULER_LEADER_LOCK_KEY,)
    assert calls[0][1] != (_SCHEMA_INIT_LOCK_KEY,)


def test_acquire_scheduler_leader_lock_closes_connection_when_already_held_by_another_worker(monkeypatch):
    """Requirement 2 (lock contention): pg_try_advisory_lock returning
    false means another worker already won - this worker's own
    connection serves no further purpose and must be released
    immediately rather than held open and leaked."""
    calls = []
    fake_conn = _FakeAdvisoryConnection(calls, fetchone_result=(False,))
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)

    result = acquire_scheduler_leader_lock()

    assert result is False
    assert fake_conn.closed is True
    assert infra_config._scheduler_leader_lock_conn is None


def test_acquire_scheduler_leader_lock_fails_open_when_postgres_is_unreachable(monkeypatch):
    """Requirement 3 + 5 (connection failure, fail-open behavior): if
    `psycopg2.connect` itself raises (PostgreSQL unreachable), this
    single-worker/local-dev case must keep working exactly as before
    multi-worker dedup existed - matches this function's own documented
    fail-open contract. No connection was ever opened, so there is
    nothing to leak here."""
    def _raise_connect(**kw):
        raise OSError("simulated: connection refused")

    monkeypatch.setattr("psycopg2.connect", _raise_connect)

    result = acquire_scheduler_leader_lock()

    assert result is True
    assert infra_config._scheduler_leader_lock_conn is None


def test_acquire_scheduler_leader_lock_fails_open_when_the_query_itself_fails(monkeypatch):
    """Requirement 3 + 5, distinct from the connect-failure case above:
    `psycopg2.connect` succeeds but `pg_try_advisory_lock` itself raises
    (e.g. the connection drops mid-query). The current implementation's
    `except Exception: return True` is a single broad handler around the
    whole connect-and-query sequence, so this still fails open exactly
    like an unreachable database - characterizing this as implemented,
    not as an idealized contract.

    This is also a genuine resource-safety gap worth flagging (see the
    Required Report's "discrepancy" section): unlike the
    lock-already-held branch above, the `conn` opened here is never
    closed on this path - it is a local variable, never assigned to the
    module global (only the `if acquired:` branch does that), so nothing
    in this process can close it later via release_scheduler_leader_lock()
    either. This test documents that as current behavior; it does not
    change production code to fix it."""
    calls = []
    fake_conn = _FakeAdvisoryConnection(
        calls, raise_on_execute=OSError("simulated: connection dropped mid-query"),
    )
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)

    result = acquire_scheduler_leader_lock()

    assert result is True
    assert infra_config._scheduler_leader_lock_conn is None
    # Documents the gap: the opened connection is left unclosed on this
    # specific failure path (contrast with the lock-contention test
    # above, where close() IS called).
    assert fake_conn.closed is False


def test_release_scheduler_leader_lock_closes_connection_and_clears_global(monkeypatch):
    """Requirement 4 (cleanup on success): the connection deliberately
    held open by a successful acquire is released on shutdown."""
    calls = []
    fake_conn = _FakeAdvisoryConnection(calls, fetchone_result=(True,))
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)
    acquire_scheduler_leader_lock()

    release_scheduler_leader_lock()

    assert fake_conn.closed is True
    assert infra_config._scheduler_leader_lock_conn is None


def test_release_scheduler_leader_lock_is_a_safe_noop_when_nothing_is_held():
    """A non-leader worker (or a leader that already released) must be
    able to call this during shutdown without error."""
    release_scheduler_leader_lock()

    assert infra_config._scheduler_leader_lock_conn is None


def test_release_scheduler_leader_lock_tolerates_close_raising_and_still_clears_global(monkeypatch):
    """Requirement 4 (cleanup on failure): even if the held connection's
    own close() raises (e.g. the socket is already dead), shutdown must
    not crash, and the module must not keep believing a now-unusable
    connection is still the held lock."""
    calls = []
    fake_conn = _FakeAdvisoryConnection(calls, fetchone_result=(True,))
    monkeypatch.setattr("psycopg2.connect", lambda **kw: fake_conn)
    acquire_scheduler_leader_lock()
    fake_conn._raise_on_close = OSError("simulated: socket already closed")

    release_scheduler_leader_lock()  # must not raise

    assert infra_config._scheduler_leader_lock_conn is None
