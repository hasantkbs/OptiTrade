"""
Tests proving every `psycopg2.pool.ThreadedConnectionPool(...)`
construction site in this backend now sets an explicit
`connect_timeout` (production audit E2E chaos test: psycopg2/libpq has
NO default TCP-level connect timeout of its own - verified live, a
connection attempt to an unreachable-but-not-actively-refusing address
(a network partition, not "the service is down and refusing
connections", which psycopg2 already fails in under a millisecond)
hung past 20 seconds with no way to bound it, when constructed exactly
as every `ThreadedConnectionPool(...)` call in this codebase previously
did. Every request this backend serves runs through a bounded thread
pool (see main.py's `_executor`); one such hang per in-flight Postgres
connection attempt would exhaust it far faster than any of this
codebase's existing per-repository failure isolation was designed to
tolerate. See core/infra_config.py::postgres_connect_timeout_seconds()'s
docstring.

Each shape-check test constructs the real repository (no explicit
`config=`/pool override) so the actual construction code path runs,
then inspects `ThreadedConnectionPool`'s own `_kwargs` (psycopg2 stores
every keyword argument passed to `AbstractConnectionPool.__init__`
verbatim there) to confirm `connect_timeout` was actually threaded
through - not merely that some unrelated default happens to apply.
"""
import time

import psycopg2
import pytest

_CONFIGURED_TIMEOUT = 3


@pytest.fixture(autouse=True)
def _configured_postgres_connect_timeout(monkeypatch):
    monkeypatch.setenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", str(_CONFIGURED_TIMEOUT))


def _assert_pool_has_the_configured_connect_timeout(pool) -> None:
    assert pool._kwargs.get("connect_timeout") == _CONFIGURED_TIMEOUT


def test_postgres_repository_base_pool_has_the_configured_connect_timeout():
    """Covers feature_store/offline_store.py and decision_engine/repository.py transitively - both are built on this shared base."""
    from core.postgres_repository_base import PostgresRepositoryBase
    repo = PostgresRepositoryBase(schema_statements=[])
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_portfolio_repository_pool_has_the_configured_connect_timeout():
    from portfolio.repository import PortfolioRepository
    repo = PortfolioRepository()
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_model_serving_rollback_repository_pool_has_the_configured_connect_timeout():
    from model_serving.rollback import RollbackRepository
    repo = RollbackRepository()
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_paper_trading_repository_pool_has_the_configured_connect_timeout():
    from paper_trading.repository import PaperTradingRepository
    repo = PaperTradingRepository()
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_users_repository_pool_has_the_configured_connect_timeout():
    from users.repository import UsersRepository
    repo = UsersRepository()
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_watchlist_repository_pool_has_the_configured_connect_timeout():
    from watchlist.repository import WatchlistRepository
    repo = WatchlistRepository()
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_learning_persistence_repository_pool_has_the_configured_connect_timeout():
    from learning.persistence import LearningRepository
    repo = LearningRepository()
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_dashboard_repository_pool_has_the_configured_connect_timeout():
    from dashboard.repository import DashboardRepository
    repo = DashboardRepository()
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_research_lab_base_repository_pool_has_the_configured_connect_timeout():
    from research_lab.base_repository import PostgresRepositoryBase as ResearchLabPostgresRepositoryBase
    repo = ResearchLabPostgresRepositoryBase(schema_statements=[])
    try:
        _assert_pool_has_the_configured_connect_timeout(repo._pool)
    finally:
        repo.close()


def test_default_connect_timeout_is_five_seconds_when_unconfigured(monkeypatch):
    monkeypatch.delenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", raising=False)
    from portfolio.repository import PortfolioRepository
    repo = PortfolioRepository()
    try:
        assert repo._pool._kwargs.get("connect_timeout") == 5
    finally:
        repo.close()


def test_an_unreachable_postgres_host_is_bounded_by_the_configured_connect_timeout():
    """The actual chaos-test proof, not just a config-shape check: a
    blackholed (not connection-refused) address gets no TCP RST, so
    without an explicit connect_timeout the OS's own SYN-retry timeout
    (~127s+ on Linux) governs how long a caller waits - verified live,
    this previously hung past 20 seconds. With connect_timeout passed
    explicitly, the failure must surface close to that bound, not
    anywhere near the unbounded OS default."""
    started_at = time.perf_counter()
    with pytest.raises(psycopg2.OperationalError):
        psycopg2.connect(
            host="240.0.0.1", port=5432, dbname="optitrade", user="optitrade_user", password="",
            connect_timeout=_CONFIGURED_TIMEOUT,
        )
    elapsed = time.perf_counter() - started_at
    assert elapsed < _CONFIGURED_TIMEOUT + 3.0
