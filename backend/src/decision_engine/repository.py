"""
OptiTrade Decision Engine — execution persistence.

Every completed decision is stored for future learning (a later
Continuous Learning step reads this history back to recompute per-engine
accuracy, which then feeds `weighting.AccuracyWeightProvider` via the
Feature Store). Uses the same PostgreSQL database as the Feature Store
(`feature_store.config.FeatureStoreConfig`'s connection settings) and the
same idempotent-schema convention as `feature_store/offline_store.py` and
`core/monitoring.py::init_db()` — no separate migration framework.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from core.infra_config import postgres_pool_size_from_env
from core.postgres_repository_base import PostgresRepositoryBase
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.exceptions import ExecutionPersistenceError
from decision_engine.models import DecisionOutput
from feature_store.config import FeatureStoreConfig

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS decision_engine_executions (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    decision VARCHAR(8) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    expected_return DOUBLE PRECISION NOT NULL,
    expected_volatility DOUBLE PRECISION NOT NULL,
    aggregation_strategy_version VARCHAR(64) NOT NULL,
    data_sufficiency DOUBLE PRECISION NOT NULL,
    evidence JSONB NOT NULL,
    engine_results JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_decision_engine_executions_lookup
    ON decision_engine_executions (symbol, timestamp DESC);
"""

# `decision_engine_executions` is written once per completed decision,
# forever - nothing here consumes it by time window (`get_recent` is a
# fixed-`limit` lookup, and per-engine accuracy is computed from
# `learning_engine_outcomes`, a separate table, not this one), so 365
# days is a generous, safe default with no known downstream dependency
# on it. See `purge_old_executions()`.
_DEFAULT_EXECUTION_HISTORY_RETENTION_DAYS = int(
    os.getenv("DECISION_ENGINE_EXECUTION_HISTORY_RETENTION_DAYS", "365")
)


class PostgresExecutionRepository(PostgresRepositoryBase):
    """Stores and retrieves completed `DecisionOutput`s."""

    def __init__(
        self,
        config: Optional[FeatureStoreConfig] = None,
        minconn: Optional[int] = None,
        maxconn: Optional[int] = None,
    ) -> None:
        if minconn is None or maxconn is None:
            env_minconn, env_maxconn = postgres_pool_size_from_env("DECISION_ENGINE", 1, 5)
            minconn = env_minconn if minconn is None else minconn
            maxconn = env_maxconn if maxconn is None else maxconn
        super().__init__(
            schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL],
            config=config,
            minconn=minconn,
            maxconn=maxconn,
        )

    def save(self, output: DecisionOutput) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO decision_engine_executions
                        (symbol, decision, confidence, expected_return, expected_volatility,
                         aggregation_strategy_version, data_sufficiency, evidence,
                         engine_results, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        output.symbol,
                        output.decision.value,
                        output.confidence,
                        output.expected_return,
                        output.expected_volatility,
                        output.aggregation_strategy_version,
                        output.data_sufficiency,
                        json.dumps(output.evidence),
                        json.dumps([vote.model_dump(mode="json") for vote in output.engine_results]),
                        output.timestamp,
                    ),
                )
        except psycopg2.Error as exc:
            log_event(
                logger,
                component="decision_engine",
                module="decision_engine.repository",
                operation="save",
                status=STATUS_ERROR,
                symbol=output.symbol,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.ERROR,
            )
            raise ExecutionPersistenceError(f"failed to persist decision execution: {exc}") from exc
        else:
            log_event(
                logger,
                component="decision_engine",
                module="decision_engine.repository",
                operation="save",
                status=STATUS_SUCCESS,
                symbol=output.symbol,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
            )

    def get_recent(self, symbol: str, limit: int = 10) -> List[DecisionOutput]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT symbol, decision, confidence, expected_return, expected_volatility,
                           aggregation_strategy_version, data_sufficiency, evidence,
                           engine_results, timestamp
                    FROM decision_engine_executions
                    WHERE symbol = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (symbol, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            log_event(
                logger,
                component="decision_engine",
                module="decision_engine.repository",
                operation="get_recent",
                status=STATUS_ERROR,
                symbol=symbol,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.ERROR,
            )
            raise ExecutionPersistenceError(f"failed to query decision executions: {exc}") from exc

        log_event(
            logger,
            component="decision_engine",
            module="decision_engine.repository",
            operation="get_recent",
            status=STATUS_SUCCESS,
            symbol=symbol,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return [
            DecisionOutput(
                symbol=row["symbol"],
                decision=row["decision"],
                confidence=row["confidence"],
                expected_return=row["expected_return"],
                expected_volatility=row["expected_volatility"],
                aggregation_strategy_version=row["aggregation_strategy_version"],
                data_sufficiency=row["data_sufficiency"],
                evidence=row["evidence"],
                engine_results=row["engine_results"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def purge_old_executions(self, retention_days: Optional[int] = None) -> int:
        """Deletes execution rows older than the retention window.
        Returns the number of rows deleted."""
        retention_days = (
            retention_days if retention_days is not None else _DEFAULT_EXECUTION_HISTORY_RETENTION_DAYS
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute("DELETE FROM decision_engine_executions WHERE timestamp < %s", (cutoff,))
                deleted = cur.rowcount
        except psycopg2.Error as exc:
            log_event(
                logger,
                component="decision_engine",
                module="decision_engine.repository",
                operation="purge_old_executions",
                status=STATUS_ERROR,
                error_type=type(exc).__name__,
                execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.ERROR,
            )
            raise ExecutionPersistenceError(f"failed to purge decision executions: {exc}") from exc

        log_event(
            logger,
            component="decision_engine",
            module="decision_engine.repository",
            operation="purge_old_executions",
            status=STATUS_SUCCESS,
            deleted_count=deleted,
            retention_days=retention_days,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return deleted
