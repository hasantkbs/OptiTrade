"""
OptiTrade Feature Store — PostgreSQL-backed offline store.

The single source of truth: every write is an immutable, append-only row
keyed by (symbol, feature_name, version, event_timestamp,
ingestion_timestamp) — nothing is ever UPDATEd or DELETEd in the normal
write path, so a point-in-time query made today returns the exact same
answer it would have returned on the day in question, regardless of what
has been written since.

Schema management follows this project's existing convention
(`core/monitoring.py::init_db()`): idempotent `CREATE TABLE IF NOT
EXISTS`/`CREATE INDEX IF NOT EXISTS` statements run once at construction,
no separate migration framework.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, List, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.config import FeatureStoreConfig
from feature_store.exceptions import FeatureStoreError
from feature_store.models import FeatureRecord

logger = logging.getLogger(__name__)

_MISS = "miss"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feature_store_records (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    feature_name VARCHAR(128) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    version VARCHAR(32) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    ingestion_timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_feature_store_lookup
    ON feature_store_records (symbol, feature_name, event_timestamp DESC, ingestion_timestamp DESC);
"""


class PostgresOfflineStore:
    """Offline (durable, versioned, point-in-time-queryable) feature store
    backed by PostgreSQL. Thread-safe: uses a `ThreadedConnectionPool`
    since the application already runs analysis work across a
    `ThreadPoolExecutor` (see `main.py::_parallel_scan`)."""

    def __init__(
        self,
        config: Optional[FeatureStoreConfig] = None,
        minconn: int = 1,
        maxconn: int = 5,
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
        )
        self._init_schema()

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        """Acquires a pooled connection and always returns it — including
        when acquisition itself fails (e.g. the pool is closed or
        exhausted), which is why this wraps `getconn()` too, not just the
        query that follows it."""
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def _init_schema(self) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
            cur.execute(_CREATE_INDEX_SQL)

    def insert(self, record: FeatureRecord) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feature_store_records
                        (symbol, feature_name, value, version, event_timestamp, ingestion_timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.symbol,
                        record.feature_name,
                        record.value,
                        record.version,
                        record.event_timestamp,
                        record.ingestion_timestamp,
                    ),
                )
        except psycopg2.Error as exc:
            log_event(
                logger,
                component="feature_store",
                module="feature_store.offline_store",
                operation="insert",
                status=STATUS_ERROR,
                symbol=record.symbol,
                feature_name=record.feature_name,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.ERROR,
            )
            raise FeatureStoreError(f"failed to insert feature record: {exc}") from exc
        else:
            log_event(
                logger,
                component="feature_store",
                module="feature_store.offline_store",
                operation="insert",
                status=STATUS_SUCCESS,
                symbol=record.symbol,
                feature_name=record.feature_name,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
            )

    def get_latest(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]:
        return self.get_as_of(symbol, feature_name, datetime.now(timezone.utc))

    def get_as_of(
        self, symbol: str, feature_name: str, as_of: datetime
    ) -> Optional[FeatureRecord]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT symbol, feature_name, value, version, event_timestamp, ingestion_timestamp
                    FROM feature_store_records
                    WHERE symbol = %s AND feature_name = %s AND event_timestamp <= %s
                    ORDER BY event_timestamp DESC, ingestion_timestamp DESC
                    LIMIT 1
                    """,
                    (symbol, feature_name, as_of),
                )
                row = cur.fetchone()
        except psycopg2.Error as exc:
            log_event(
                logger,
                component="feature_store",
                module="feature_store.offline_store",
                operation="get_as_of",
                status=STATUS_ERROR,
                symbol=symbol,
                feature_name=feature_name,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.ERROR,
            )
            raise FeatureStoreError(f"failed to query feature record: {exc}") from exc

        log_event(
            logger,
            component="feature_store",
            module="feature_store.offline_store",
            operation="get_as_of",
            status=STATUS_SUCCESS if row is not None else _MISS,
            symbol=symbol,
            feature_name=feature_name,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        if row is None:
            return None
        return FeatureRecord(**dict(row))

    def list_feature_names(self, symbol: str) -> List[str]:
        """Every distinct `feature_name` ever recorded for `symbol` -
        used by offline consumers (e.g. the ML Training Platform's
        feature extractor) that need to auto-discover whatever
        features currently exist for a symbol, including ones added
        after this method itself was written, rather than depending on
        a hardcoded list."""
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT feature_name FROM feature_store_records WHERE symbol = %s",
                    (symbol,),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            log_event(
                logger,
                component="feature_store",
                module="feature_store.offline_store",
                operation="list_feature_names",
                status=STATUS_ERROR,
                symbol=symbol,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.ERROR,
            )
            raise FeatureStoreError(f"failed to list feature names: {exc}") from exc

        log_event(
            logger,
            component="feature_store",
            module="feature_store.offline_store",
            operation="list_feature_names",
            status=STATUS_SUCCESS,
            symbol=symbol,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
            row_count=len(rows),
        )
        return [row[0] for row in rows]

    def get_history(
        self, symbol: str, feature_name: str, start: datetime, end: datetime
    ) -> List[FeatureRecord]:
        """Every recorded value for `(symbol, feature_name)` with
        `event_timestamp` in `[start, end]`, oldest first - used by
        offline research/analysis (feature correlation, stability,
        drift) rather than any live read path, which only ever needs
        `get_latest`/`get_as_of`."""
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT symbol, feature_name, value, version, event_timestamp, ingestion_timestamp
                    FROM feature_store_records
                    WHERE symbol = %s AND feature_name = %s
                      AND event_timestamp >= %s AND event_timestamp <= %s
                    ORDER BY event_timestamp ASC
                    """,
                    (symbol, feature_name, start, end),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            log_event(
                logger,
                component="feature_store",
                module="feature_store.offline_store",
                operation="get_history",
                status=STATUS_ERROR,
                symbol=symbol,
                feature_name=feature_name,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.ERROR,
            )
            raise FeatureStoreError(f"failed to query feature history: {exc}") from exc

        log_event(
            logger,
            component="feature_store",
            module="feature_store.offline_store",
            operation="get_history",
            status=STATUS_SUCCESS,
            symbol=symbol,
            feature_name=feature_name,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
            row_count=len(rows),
        )
        return [FeatureRecord(**dict(row)) for row in rows]

    def ping(self) -> bool:
        """Connectivity check used by `FeatureStoreService.health_check()`."""
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()
