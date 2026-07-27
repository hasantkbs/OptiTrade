"""OptiTrade Research Lab — experiment persistence."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import Experiment, ExperimentStatus

logger = logging.getLogger(__name__)

_MODULE = "research_lab.experiments.repository"
_COMPONENT = "research_lab"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_experiments (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    hypothesis_id BIGINT,
    author VARCHAR(128) NOT NULL,
    status VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_experiments_status
    ON research_experiments (status, created_at DESC);
"""


class ExperimentRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, experiment: Experiment) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_experiments
                        (name, description, hypothesis_id, author, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        experiment.name, experiment.description, experiment.hypothesis_id, experiment.author,
                        experiment.status.value, experiment.created_at, experiment.updated_at,
                    ),
                )
                experiment_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at)
            raise self._wrap("save experiment", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, experiment_id=experiment_id)
        return experiment_id

    def get(self, experiment_id: int) -> Optional[Experiment]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM research_experiments WHERE id = %s", (experiment_id,))
                row = cur.fetchone()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get", exc, started_at)
            raise self._wrap("get experiment", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "get", started_at)
        return self._row_to_model(row) if row else None

    def update_status(self, experiment_id: int, status: ExperimentStatus, updated_at: datetime) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE research_experiments SET status = %s, updated_at = %s WHERE id = %s",
                    (status.value, updated_at, experiment_id),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "update_status", exc, started_at, experiment_id=experiment_id)
            raise self._wrap("update experiment status", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "update_status", started_at, experiment_id=experiment_id, new_status=status.value)

    def list_by_status(self, status: Optional[ExperimentStatus] = None, limit: int = 100) -> List[Experiment]:
        started_at = time.perf_counter()
        query = "SELECT * FROM research_experiments"
        params: tuple = ()
        if status is not None:
            query += " WHERE status = %s"
            params = (status.value,)
        query += " ORDER BY created_at DESC LIMIT %s"
        params = params + (limit,)

        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_by_status", exc, started_at)
            raise self._wrap("list experiments", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_by_status", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> Experiment:
        return Experiment(
            id=row["id"], name=row["name"], description=row["description"], hypothesis_id=row["hypothesis_id"],
            author=row["author"], status=ExperimentStatus(row["status"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
