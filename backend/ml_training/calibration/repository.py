"""OptiTrade ML Training Platform — calibration result persistence."""
from __future__ import annotations

import logging
import time
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ml_training.exceptions import MLTrainingPersistenceError
from ml_training.models import CalibrationMethod, CalibrationResult
from research_lab.base_repository import PostgresRepositoryBase

logger = logging.getLogger(__name__)

_MODULE = "ml_training.calibration.repository"
_COMPONENT = "ml_training"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ml_training_calibration_results (
    id BIGSERIAL PRIMARY KEY,
    model_id VARCHAR(128) NOT NULL,
    method VARCHAR(16) NOT NULL,
    calibration_error_before DOUBLE PRECISION NOT NULL,
    calibration_error_after DOUBLE PRECISION NOT NULL,
    artifact_path TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_ml_training_calibration_results_lookup
    ON ml_training_calibration_results (model_id, computed_at DESC);
"""


class CalibrationRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, result: CalibrationResult) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ml_training_calibration_results
                        (model_id, method, calibration_error_before, calibration_error_after,
                         artifact_path, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        result.model_id, result.method.value, result.calibration_error_before,
                        result.calibration_error_after, result.artifact_path, result.computed_at,
                    ),
                )
                result_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at, model_id=result.model_id)
            raise MLTrainingPersistenceError(f"failed to save calibration result: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, result_id=result_id)
        return result_id

    def get_latest(self, model_id: str) -> Optional[CalibrationResult]:
        history = self.list_for_model(model_id, limit=1)
        return history[0] if history else None

    def list_for_model(self, model_id: str, limit: int = 20) -> List[CalibrationResult]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM ml_training_calibration_results
                    WHERE model_id = %s ORDER BY computed_at DESC LIMIT %s
                    """,
                    (model_id, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_for_model", exc, started_at, model_id=model_id)
            raise MLTrainingPersistenceError(f"failed to list calibration results: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "list_for_model", started_at, row_count=len(rows))
        return [
            CalibrationResult(
                model_id=row["model_id"], method=CalibrationMethod(row["method"]),
                calibration_error_before=row["calibration_error_before"],
                calibration_error_after=row["calibration_error_after"],
                artifact_path=row["artifact_path"], computed_at=row["computed_at"],
            )
            for row in rows
        ]
