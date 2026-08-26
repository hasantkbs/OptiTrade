"""OptiTrade Research Lab — benchmark result persistence."""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from learning.models import RollingWindow
from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import BenchmarkResult, BenchmarkSubjectType

logger = logging.getLogger(__name__)

_MODULE = "research_lab.benchmarking.repository"
_COMPONENT = "research_lab"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_benchmark_results (
    id BIGSERIAL PRIMARY KEY,
    experiment_id BIGINT,
    subject_type VARCHAR(24) NOT NULL,
    subject_a VARCHAR(128) NOT NULL,
    subject_b VARCHAR(128) NOT NULL,
    window_name VARCHAR(16) NOT NULL,
    metrics_a JSONB NOT NULL,
    metrics_b JSONB NOT NULL,
    p_value DOUBLE PRECISION NOT NULL,
    significant BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_benchmark_results_lookup
    ON research_benchmark_results (subject_type, subject_a, subject_b, created_at DESC);
"""


class BenchmarkRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, result: BenchmarkResult) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_benchmark_results
                        (experiment_id, subject_type, subject_a, subject_b, window_name, metrics_a, metrics_b,
                         p_value, significant, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        result.experiment_id, result.subject_type.value, result.subject_a, result.subject_b,
                        result.window.value, json.dumps(result.metrics_a), json.dumps(result.metrics_b),
                        result.p_value, result.significant, result.created_at,
                    ),
                )
                result_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at)
            raise self._wrap("save benchmark result", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, result_id=result_id)
        return result_id

    def list_for_subjects(
        self, subject_type: BenchmarkSubjectType, subject_a: str, subject_b: str, limit: int = 20,
    ) -> List[BenchmarkResult]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM research_benchmark_results
                    WHERE subject_type = %s AND subject_a = %s AND subject_b = %s
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (subject_type.value, subject_a, subject_b, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_for_subjects", exc, started_at)
            raise self._wrap("list benchmark results", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_for_subjects", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    def list_for_experiment(self, experiment_id: int, limit: int = 50) -> List[BenchmarkResult]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM research_benchmark_results
                    WHERE experiment_id = %s ORDER BY created_at DESC LIMIT %s
                    """,
                    (experiment_id, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_for_experiment", exc, started_at, experiment_id=experiment_id)
            raise self._wrap("list benchmark results for experiment", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_for_experiment", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> BenchmarkResult:
        return BenchmarkResult(
            id=row["id"], experiment_id=row["experiment_id"], subject_type=BenchmarkSubjectType(row["subject_type"]),
            subject_a=row["subject_a"], subject_b=row["subject_b"], window=RollingWindow(row["window_name"]),
            metrics_a=row["metrics_a"], metrics_b=row["metrics_b"], p_value=row["p_value"],
            significant=row["significant"], created_at=row["created_at"],
        )
