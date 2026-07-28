"""OptiTrade ML Training Platform — optimization result persistence."""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ml_training.exceptions import MLTrainingPersistenceError
from ml_training.models import ModelAlgorithm, OptimizationResult
from research_lab.base_repository import PostgresRepositoryBase

logger = logging.getLogger(__name__)

_MODULE = "ml_training.optimization.repository"
_COMPONENT = "ml_training"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ml_training_optimization_results (
    id BIGSERIAL PRIMARY KEY,
    model_id VARCHAR(128) NOT NULL,
    algorithm VARCHAR(24) NOT NULL,
    best_params JSONB NOT NULL,
    best_score DOUBLE PRECISION NOT NULL,
    n_trials INTEGER NOT NULL,
    study_name VARCHAR(255) NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_ml_training_optimization_results_lookup
    ON ml_training_optimization_results (model_id, computed_at DESC);
"""


class OptimizationRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, result: OptimizationResult) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ml_training_optimization_results
                        (model_id, algorithm, best_params, best_score, n_trials, study_name, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        result.model_id, result.algorithm.value, json.dumps(result.best_params),
                        result.best_score, result.n_trials, result.study_name, result.computed_at,
                    ),
                )
                result_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at, model_id=result.model_id)
            raise MLTrainingPersistenceError(f"failed to save optimization result: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, result_id=result_id)
        return result_id

    def get_latest(self, model_id: str) -> Optional[OptimizationResult]:
        history = self.list_for_model(model_id, limit=1)
        return history[0] if history else None

    def list_for_model(self, model_id: str, limit: int = 20) -> List[OptimizationResult]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM ml_training_optimization_results
                    WHERE model_id = %s ORDER BY computed_at DESC LIMIT %s
                    """,
                    (model_id, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_for_model", exc, started_at, model_id=model_id)
            raise MLTrainingPersistenceError(f"failed to list optimization results: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "list_for_model", started_at, row_count=len(rows))
        return [
            OptimizationResult(
                model_id=row["model_id"], algorithm=ModelAlgorithm(row["algorithm"]),
                best_params=row["best_params"], best_score=row["best_score"], n_trials=row["n_trials"],
                study_name=row["study_name"], computed_at=row["computed_at"],
            )
            for row in rows
        ]
