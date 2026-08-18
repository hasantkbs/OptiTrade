"""
Tests for core/postgres_repository_base.py (production audit MEDIUM #6:
`decision_engine/repository.py::PostgresExecutionRepository` and
`feature_store/offline_store.py::PostgresOfflineStore` each independently
duplicated the identical `ThreadedConnectionPool` + `_connection()`
contextmanager + idempotent-schema-on-construct boilerplate). Both now
inherit the shared infrastructure from `PostgresRepositoryBase`, while
keeping their own distinct tables, queries, and exception types.

Run against the real, local PostgreSQL instance, matching this project's
testing convention.
"""
import pytest

from core.postgres_repository_base import PostgresRepositoryBase
from decision_engine.repository import PostgresExecutionRepository
from feature_store.config import FeatureStoreConfig
from feature_store.offline_store import PostgresOfflineStore


def test_both_migrated_repositories_inherit_the_shared_base():
    assert issubclass(PostgresExecutionRepository, PostgresRepositoryBase)
    assert issubclass(PostgresOfflineStore, PostgresRepositoryBase)


def test_both_migrated_repositories_share_the_same_connection_and_lifecycle_implementation():
    # Proves the actual dedup happened - not merely two classes that
    # happen to define identically-shaped methods.
    assert PostgresExecutionRepository._connection is PostgresRepositoryBase._connection
    assert PostgresOfflineStore._connection is PostgresRepositoryBase._connection
    assert PostgresExecutionRepository.ping is PostgresRepositoryBase.ping
    assert PostgresOfflineStore.ping is PostgresRepositoryBase.ping
    assert PostgresExecutionRepository.close is PostgresRepositoryBase.close
    assert PostgresOfflineStore.close is PostgresRepositoryBase.close


def test_they_remain_two_independent_connection_pools_with_their_own_tables():
    """Consolidating the boilerplate must not merge the two into a
    shared pool or a shared table - they persist genuinely different
    domain data (decision snapshots vs. named scalar features)."""
    config = FeatureStoreConfig.from_env()
    exec_repo = PostgresExecutionRepository(config=config)
    offline_store = PostgresOfflineStore(config=config)
    try:
        assert exec_repo._pool is not offline_store._pool
        assert exec_repo.ping() is True
        assert offline_store.ping() is True

        # Closing one repository's pool must not affect the other's.
        exec_repo.close()
        assert offline_store.ping() is True
    finally:
        offline_store.close()


def test_constructor_signature_and_defaults_are_unchanged_for_existing_callers():
    """Every existing call site constructs these with either no
    arguments or `config=...` only - the `maxconn=5` default (not
    research_lab's own base class's `maxconn=3`) must be preserved."""
    config = FeatureStoreConfig.from_env()
    exec_repo = PostgresExecutionRepository(config=config)
    try:
        assert exec_repo._pool.maxconn == 5
        assert exec_repo._pool.minconn == 1
    finally:
        exec_repo.close()


def test_generic_base_class_cannot_be_used_without_schema_statements():
    with pytest.raises(TypeError):
        PostgresRepositoryBase()
