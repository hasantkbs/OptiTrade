"""
OptiTrade Research Lab — shared PostgreSQL repository base.

Every subpackage repository (experiments, hypothesis, backtesting,
benchmarking, feature_analysis, model_analysis, datasets, shadow,
promotion, reports) needs the identical `ThreadedConnectionPool` +
`_connection()` contextmanager + idempotent-schema-on-construct pattern
already used independently by `feature_store/offline_store.py`,
`decision_engine/repository.py`, and `learning/persistence.py`. With
ten repositories in this package alone, copy-pasting that pattern a
tenth time would be exactly the kind of duplication this project's
conventions exist to avoid - so it is factored into one shared base
class here instead. The three earlier, already-shipped modules are left
untouched.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator, List, Optional

import psycopg2
import psycopg2.pool

from core.infra_config import postgres_connect_timeout_seconds
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.config import FeatureStoreConfig
from research_lab.exceptions import ResearchLabPersistenceError

logger = logging.getLogger(__name__)


class PostgresRepositoryBase:
    """Base class for every Research Lab Postgres-backed repository.
    Subclasses pass their own idempotent `CREATE TABLE IF NOT EXISTS` /
    `CREATE INDEX IF NOT EXISTS` statements and get pooled connections,
    structured logging helpers, and lifecycle management for free."""

    def __init__(
        self,
        schema_statements: List[str],
        config: Optional[FeatureStoreConfig] = None,
        minconn: int = 1,
        maxconn: int = 3,
    ) -> None:
        self._config = config or FeatureStoreConfig.from_env()
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn,
            maxconn,
            host=self._config.postgres_host,
            port=self._config.postgres_port,
            dbname=self._config.postgres_db,
            user=self._config.postgres_user,
            password=self._config.postgres_password,
            connect_timeout=postgres_connect_timeout_seconds(),
        )
        self._init_schema(schema_statements)

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def _init_schema(self, schema_statements: List[str]) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            for statement in schema_statements:
                cur.execute(statement)

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()

    def _log_success(self, component: str, module: str, operation: str, started_at: float, **extra) -> None:
        log_event(
            logger, component=component, module=module, operation=operation,
            status=STATUS_SUCCESS, execution_time_ms=(time.perf_counter() - started_at) * 1000, **extra,
        )

    def _log_error(self, component: str, module: str, operation: str, exc: Exception, started_at: float, **extra) -> None:
        log_event(
            logger, component=component, module=module, operation=operation,
            status=STATUS_ERROR, error_type=type(exc).__name__,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, level=logging.ERROR, **extra,
        )

    @staticmethod
    def _wrap(operation: str, exc: Exception) -> ResearchLabPersistenceError:
        return ResearchLabPersistenceError(f"failed to {operation}: {exc}")
