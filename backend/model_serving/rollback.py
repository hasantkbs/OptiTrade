"""
OptiTrade Model Serving Platform — rollback support.

Requirement 8: allow rolling the ACTIVE model for a (label_name,
horizon_days) pair back to a previous version, and never delete
anything in the process. Rather than adding new transitions to
`ml_training.registry`'s promotion lifecycle (CANDIDATE -> SHADOW ->
ACTIVE -> ARCHIVED has no path back from ACTIVE, and ARCHIVED is
terminal by design - see `ml_training/registry/lifecycle.py`), a
rollback here is a serving-level override: a small pointer table saying
"serve this specific model_id instead of whatever the registry
considers ACTIVE", checked first by `service.py:PredictionService`
before falling back to `ModelLoader.resolve_active_entry`. Nothing in
`ml_training.registry` is ever touched, so no promotion state changes,
nothing is archived, and the model that WAS being served is trivially
still there afterwards.

Self-contained Postgres access (its own connection pool, not
`research_lab.base_repository.PostgresRepositoryBase`) matching the
convention `feature_store/offline_store.py`, `decision_engine/
repository.py`, and `learning/persistence.py` already independently
use - `model_serving` sits on the production side of the research/
production boundary (see `tests/test_research_isolation.py`), so it
must never depend on `research_lab`, even indirectly for a generic
connection-pool helper.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.config import FeatureStoreConfig
from ml_training.models import LabelName, ModelRegistryEntry
from ml_training.registry.service import ModelRegistryService
from model_serving.exceptions import InvalidRollbackError, ModelVersionNotFoundError

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS model_serving_rollback_overrides (
    label_name VARCHAR(32) NOT NULL,
    horizon_days INTEGER NOT NULL,
    model_id VARCHAR(128) NOT NULL,
    rolled_back_by VARCHAR(128) NOT NULL,
    rolled_back_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (label_name, horizon_days)
);
"""


class RollbackRepository:
    def __init__(self, config: Optional[FeatureStoreConfig] = None, minconn: int = 1, maxconn: int = 3) -> None:
        self._config = config or FeatureStoreConfig.from_env()
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn, maxconn, host=self._config.postgres_host, port=self._config.postgres_port,
            dbname=self._config.postgres_db, user=self._config.postgres_user, password=self._config.postgres_password,
        )
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def set_override(self, label_name: LabelName, horizon_days: int, model_id: str, rolled_back_by: str) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO model_serving_rollback_overrides
                        (label_name, horizon_days, model_id, rolled_back_by, rolled_back_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (label_name, horizon_days) DO UPDATE
                        SET model_id = EXCLUDED.model_id, rolled_back_by = EXCLUDED.rolled_back_by,
                            rolled_back_at = EXCLUDED.rolled_back_at
                    """,
                    (label_name.value, horizon_days, model_id, rolled_back_by, datetime.now(timezone.utc)),
                )
        except psycopg2.Error as exc:
            log_event(
                logger, component="model_serving", module="model_serving.rollback", operation="set_override",
                status=STATUS_ERROR, label_name=label_name.value, horizon_days=horizon_days,
                error_type=type(exc).__name__, execution_time_ms=(time.perf_counter() - started_at) * 1000,
                level=logging.ERROR,
            )
            raise
        log_event(
            logger, component="model_serving", module="model_serving.rollback", operation="set_override",
            status=STATUS_SUCCESS, label_name=label_name.value, horizon_days=horizon_days, model_id=model_id,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )

    def get_override(self, label_name: LabelName, horizon_days: int) -> Optional[str]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT model_id FROM model_serving_rollback_overrides WHERE label_name = %s AND horizon_days = %s",
                (label_name.value, horizon_days),
            )
            row = cur.fetchone()
        return row["model_id"] if row else None

    def clear_override(self, label_name: LabelName, horizon_days: int) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM model_serving_rollback_overrides WHERE label_name = %s AND horizon_days = %s",
                (label_name.value, horizon_days),
            )
        log_event(
            logger, component="model_serving", module="model_serving.rollback", operation="clear_override",
            status=STATUS_SUCCESS, label_name=label_name.value, horizon_days=horizon_days,
        )

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()


class RollbackService:
    """Applies/clears a rollback override. Never mutates
    `ml_training.registry` - only this package's own pointer table."""

    def __init__(
        self,
        repository: Optional[RollbackRepository] = None,
        registry_service: Optional[ModelRegistryService] = None,
    ) -> None:
        self.repository = repository or RollbackRepository()
        self.registry_service = registry_service or ModelRegistryService()

    def rollback_to(self, label_name: LabelName, horizon_days: int, model_id: str, rolled_back_by: str) -> None:
        if not rolled_back_by or not rolled_back_by.strip():
            raise InvalidRollbackError("rollback requires a non-blank rolled_back_by")

        entry = self.registry_service.get(model_id)
        if entry is None:
            raise ModelVersionNotFoundError(f"no registered model with model_id {model_id!r}")
        if entry.label_name != label_name or entry.horizon_days != horizon_days:
            raise InvalidRollbackError(
                f"model {model_id!r} is registered for label_name={entry.label_name.value!r}/"
                f"horizon_days={entry.horizon_days}, not label_name={label_name.value!r}/horizon_days={horizon_days}"
            )

        self.repository.set_override(label_name, horizon_days, model_id, rolled_back_by)

    def clear_rollback(self, label_name: LabelName, horizon_days: int) -> None:
        self.repository.clear_override(label_name, horizon_days)

    def current_override(self, label_name: LabelName, horizon_days: int) -> Optional[ModelRegistryEntry]:
        model_id = self.repository.get_override(label_name, horizon_days)
        if model_id is None:
            return None
        return self.registry_service.get(model_id)
