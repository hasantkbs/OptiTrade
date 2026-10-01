"""OptiTrade ML Training Platform — training run persistence."""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ml_training.exceptions import MLTrainingPersistenceError
from ml_training.models import (
    LabelName,
    ModelAlgorithm,
    ModelMetrics,
    TaskType,
    TrainingRun,
    TrainingRunStatus,
)
from research_lab.base_repository import PostgresRepositoryBase

logger = logging.getLogger(__name__)

_MODULE = "ml_training.runs.repository"
_COMPONENT = "ml_training"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ml_training_runs (
    id BIGSERIAL PRIMARY KEY,
    model_id VARCHAR(128) NOT NULL,
    algorithm VARCHAR(32) NOT NULL,
    task_type VARCHAR(16) NOT NULL,
    label_name VARCHAR(32) NOT NULL,
    horizon_days INTEGER NOT NULL,
    dataset_id BIGINT,
    hyperparameters JSONB NOT NULL,
    metrics JSONB,
    feature_list JSONB NOT NULL,
    status VARCHAR(16) NOT NULL,
    experiment_id BIGINT,
    artifact_path TEXT,
    training_date TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_ml_training_runs_experiment
    ON ml_training_runs (experiment_id, training_date DESC);
"""


class TrainingRunRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, run: TrainingRun) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ml_training_runs
                        (model_id, algorithm, task_type, label_name, horizon_days, dataset_id,
                         hyperparameters, metrics, feature_list, status, experiment_id, artifact_path,
                         training_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        run.model_id, run.algorithm.value, run.task_type.value, run.label_name.value,
                        run.horizon_days, run.dataset_id, json.dumps(run.hyperparameters),
                        json.dumps(run.metrics.model_dump()) if run.metrics is not None else None,
                        json.dumps(run.feature_list), run.status.value, run.experiment_id,
                        run.artifact_path, run.training_date,
                    ),
                )
                run_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at, model_id=run.model_id)
            raise MLTrainingPersistenceError(f"failed to save training run: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, run_id=run_id)
        return run_id

    def update(self, run: TrainingRun) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ml_training_runs
                    SET hyperparameters = %s, metrics = %s, feature_list = %s, status = %s, artifact_path = %s
                    WHERE id = %s
                    """,
                    (
                        json.dumps(run.hyperparameters),
                        json.dumps(run.metrics.model_dump()) if run.metrics is not None else None,
                        json.dumps(run.feature_list), run.status.value, run.artifact_path, run.id,
                    ),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "update", exc, started_at, run_id=run.id)
            raise MLTrainingPersistenceError(f"failed to update training run: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "update", started_at, run_id=run.id, run_status=run.status.value)

    def get(self, run_id: int) -> Optional[TrainingRun]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM ml_training_runs WHERE id = %s", (run_id,))
                row = cur.fetchone()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get", exc, started_at, run_id=run_id)
            raise MLTrainingPersistenceError(f"failed to get training run: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "get", started_at)
        return self._row_to_model(row) if row else None

    def list_for_experiment(self, experiment_id: int, limit: int = 50) -> List[TrainingRun]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM ml_training_runs
                    WHERE experiment_id = %s ORDER BY training_date DESC LIMIT %s
                    """,
                    (experiment_id, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_for_experiment", exc, started_at, experiment_id=experiment_id)
            raise MLTrainingPersistenceError(f"failed to list training runs: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "list_for_experiment", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> TrainingRun:
        return TrainingRun(
            id=row["id"], model_id=row["model_id"], algorithm=ModelAlgorithm(row["algorithm"]),
            task_type=TaskType(row["task_type"]), label_name=LabelName(row["label_name"]),
            horizon_days=row["horizon_days"], dataset_id=row["dataset_id"],
            hyperparameters=row["hyperparameters"],
            metrics=ModelMetrics(**row["metrics"]) if row["metrics"] is not None else None,
            feature_list=row["feature_list"], status=TrainingRunStatus(row["status"]),
            experiment_id=row["experiment_id"], artifact_path=row["artifact_path"],
            training_date=row["training_date"],
        )
