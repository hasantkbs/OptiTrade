"""
OptiTrade — shared PostgreSQL repository base (production side).

Mirrors `research_lab.base_repository.PostgresRepositoryBase`'s exact
"`ThreadedConnectionPool` + `_connection()` contextmanager + idempotent-
schema-on-construct pattern" (that module's own docstring names
`feature_store/offline_store.py`, `decision_engine/repository.py`, and
`learning/persistence.py` as the three production repositories already
independently duplicating it) - but living in `core/` instead of
`research_lab/`, since production code must never import `research_lab`
(see `tests/test_research_isolation.py`), even for a generic
connection-pool helper.

Only `feature_store/offline_store.py` and `decision_engine/repository.py`
are migrated onto this base for now (production audit MEDIUM #6) - they
store genuinely different data (a single named scalar feature vs. a
full decision snapshot with nested JSONB) in different tables with
different query shapes, so this only consolidates the shared
connection-pool INFRASTRUCTURE, not the domain persistence logic
itself, which stays exactly as each already had it (own queries, own
exception types, own callers, own schema).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, List, Optional

import psycopg2
import psycopg2.pool

if TYPE_CHECKING:
    from feature_store.config import FeatureStoreConfig

logger = logging.getLogger(__name__)


class PostgresRepositoryBase:
    """Base class for a production Postgres-backed repository.
    Subclasses pass their own idempotent `CREATE TABLE IF NOT EXISTS` /
    `CREATE INDEX IF NOT EXISTS` statements and get pooled connections
    and lifecycle management (`ping()`/`close()`) for free. Each
    subclass keeps its own domain queries and its own exception type."""

    def __init__(
        self,
        schema_statements: List[str],
        config: Optional[FeatureStoreConfig] = None,
        minconn: int = 1,
        maxconn: int = 5,
    ) -> None:
        # Deferred: `feature_store.config` pulls in the `feature_store`
        # package's `__init__.py`, which (via `service.py` ->
        # `offline_store.py`) imports THIS module - a module-level
        # import here would be a circular import at import time. By
        # runtime (when a repository is actually constructed) every
        # module involved has already finished loading.
        from feature_store.config import FeatureStoreConfig

        from core.infra_config import postgres_connect_timeout_seconds

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
        self._schema_statements = schema_statements
        self._init_schema()

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def _init_schema(self, schema_statements: Optional[List[str]] = None) -> None:
        """Idempotent - `CREATE TABLE/INDEX IF NOT EXISTS`, safe to call
        again after construction (existing repositories' own tests do
        exactly that, with no arguments, to prove idempotency)."""
        statements = schema_statements if schema_statements is not None else self._schema_statements
        with self._connection() as conn, conn, conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()
