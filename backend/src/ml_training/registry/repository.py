"""
OptiTrade ML Training Platform — model registry persistence.

Reuses `research_lab.base_repository.PostgresRepositoryBase` directly,
matching every other repository in this platform. `model_id` is
unique - a registry entry is created once (as CANDIDATE) and then only
ever has its promotion state updated in place, never re-inserted.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Iterator, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ml_training.exceptions import MLTrainingPersistenceError
from ml_training.models import (
    LabelName,
    ModelAlgorithm,
    ModelMetrics,
    ModelRegistryEntry,
    PromotionState,
)
from research_lab.base_repository import PostgresRepositoryBase

logger = logging.getLogger(__name__)

_MODULE = "ml_training.registry.repository"
_COMPONENT = "ml_training"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ml_training_model_registry (
    id BIGSERIAL PRIMARY KEY,
    model_id VARCHAR(128) NOT NULL UNIQUE,
    algorithm VARCHAR(32) NOT NULL,
    version VARCHAR(32) NOT NULL,
    dataset_id BIGINT,
    hyperparameters JSONB NOT NULL,
    metrics JSONB,
    feature_list JSONB NOT NULL,
    label_name VARCHAR(32) NOT NULL,
    horizon_days INTEGER NOT NULL,
    training_date TIMESTAMPTZ NOT NULL,
    promotion_state VARCHAR(16) NOT NULL,
    engine_name VARCHAR(128) NOT NULL,
    engine_version VARCHAR(32) NOT NULL,
    artifact_path TEXT NOT NULL,
    approved_by VARCHAR(128),
    promoted_at TIMESTAMPTZ
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_ml_training_model_registry_state
    ON ml_training_model_registry (promotion_state, training_date DESC);
"""


class ModelRegistryRepository(PostgresRepositoryBase):
    def __init__(self, config=None, minconn: int = 1, maxconn: int = 3) -> None:
        super().__init__(
            schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config, minconn=minconn, maxconn=maxconn,
        )

    def save(self, entry: ModelRegistryEntry) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ml_training_model_registry
                        (model_id, algorithm, version, dataset_id, hyperparameters, metrics, feature_list,
                         label_name, horizon_days, training_date, promotion_state, engine_name, engine_version,
                         artifact_path, approved_by, promoted_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        entry.model_id, entry.algorithm.value, entry.version, entry.dataset_id,
                        json.dumps(entry.hyperparameters),
                        json.dumps(entry.metrics.model_dump()) if entry.metrics is not None else None,
                        json.dumps(entry.feature_list), entry.label_name.value, entry.horizon_days,
                        entry.training_date, entry.promotion_state.value, entry.engine_name,
                        entry.engine_version, entry.artifact_path, entry.approved_by, entry.promoted_at,
                    ),
                )
                entry_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at, model_id=entry.model_id)
            raise MLTrainingPersistenceError(f"failed to save model registry entry: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, entry_id=entry_id)
        return entry_id

    def get(self, model_id: str) -> Optional[ModelRegistryEntry]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM ml_training_model_registry WHERE model_id = %s", (model_id,))
                row = cur.fetchone()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get", exc, started_at, model_id=model_id)
            raise MLTrainingPersistenceError(f"failed to get model registry entry: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "get", started_at)
        return self._row_to_model(row) if row else None

    def list_by_state(self, promotion_state: Optional[PromotionState] = None, limit: int = 50) -> List[ModelRegistryEntry]:
        started_at = time.perf_counter()
        query = "SELECT * FROM ml_training_model_registry"
        params: tuple = ()
        if promotion_state is not None:
            query += " WHERE promotion_state = %s"
            params = (promotion_state.value,)
        query += " ORDER BY training_date DESC LIMIT %s"
        params = params + (limit,)

        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_by_state", exc, started_at)
            raise MLTrainingPersistenceError(f"failed to list model registry entries: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "list_by_state", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    def update_promotion_state(
        self, model_id: str, promotion_state: PromotionState, approved_by: Optional[str], promoted_at,
    ) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ml_training_model_registry
                    SET promotion_state = %s, approved_by = %s, promoted_at = %s
                    WHERE model_id = %s
                    """,
                    (promotion_state.value, approved_by, promoted_at, model_id),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "update_promotion_state", exc, started_at, model_id=model_id)
            raise MLTrainingPersistenceError(f"failed to update model registry promotion state: {exc}") from exc
        self._log_success(
            _COMPONENT, _MODULE, "update_promotion_state", started_at,
            model_id=model_id, promotion_state=promotion_state.value,
        )

    # ── Locked group access (promote_to_active - see registry/service.py) ──
    #
    # Promoting a model to ACTIVE must never let two models end up ACTIVE
    # at once for the same (label_name, horizon_days): demoting whatever
    # was previously ACTIVE and activating the new one must happen
    # atomically, and two concurrent promotions for the same group must
    # serialize against each other (a TOCTOU race otherwise). Mirrors
    # `portfolio.repository.PortfolioRepository.locked_portfolio` - a
    # row-level lock scoped to one group, not a table-wide/global lock,
    # so unrelated (label_name, horizon_days) groups stay fully concurrent.

    @contextmanager
    def locked_group(self, label_name: LabelName, horizon_days: int) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM ml_training_model_registry WHERE label_name = %s AND horizon_days = %s "
                        "FOR UPDATE",
                        (label_name.value, horizon_days),
                    )
                yield conn
        finally:
            self._pool.putconn(conn)

    def get_locked(self, conn: "psycopg2.extensions.connection", model_id: str) -> Optional[ModelRegistryEntry]:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM ml_training_model_registry WHERE model_id = %s", (model_id,))
            row = cur.fetchone()
        return self._row_to_model(row) if row else None

    def list_active_in_group_locked(
        self, conn: "psycopg2.extensions.connection", label_name: LabelName, horizon_days: int,
    ) -> List[ModelRegistryEntry]:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM ml_training_model_registry "
                "WHERE label_name = %s AND horizon_days = %s AND promotion_state = %s",
                (label_name.value, horizon_days, PromotionState.ACTIVE.value),
            )
            rows = cur.fetchall()
        return [self._row_to_model(row) for row in rows]

    def update_promotion_state_locked(
        self, conn: "psycopg2.extensions.connection", model_id: str, promotion_state: PromotionState,
        approved_by: Optional[str], promoted_at,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ml_training_model_registry
                SET promotion_state = %s, approved_by = %s, promoted_at = %s
                WHERE model_id = %s
                """,
                (promotion_state.value, approved_by, promoted_at, model_id),
            )

    @staticmethod
    def _row_to_model(row: dict) -> ModelRegistryEntry:
        return ModelRegistryEntry(
            id=row["id"], model_id=row["model_id"], algorithm=ModelAlgorithm(row["algorithm"]),
            version=row["version"], dataset_id=row["dataset_id"], hyperparameters=row["hyperparameters"],
            metrics=ModelMetrics(**row["metrics"]) if row["metrics"] is not None else None,
            feature_list=row["feature_list"], label_name=LabelName(row["label_name"]),
            horizon_days=row["horizon_days"], training_date=row["training_date"],
            promotion_state=PromotionState(row["promotion_state"]), engine_name=row["engine_name"],
            engine_version=row["engine_version"], artifact_path=row["artifact_path"],
            approved_by=row["approved_by"], promoted_at=row["promoted_at"],
        )
