"""
OptiTrade ML Training Platform — dataset version persistence.

Only the dataset *definition/metadata* is persisted - the actual
training samples are always rebuilt on demand from the Feature Store
(via `builder.py`), matching `research_lab.datasets`'s "definition
only, never a data copy" philosophy. Reuses
`research_lab.base_repository.PostgresRepositoryBase` directly rather
than re-implementing the same connection-pool boilerplate a second
time in this allied, equally-offline package.
"""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ml_training.exceptions import MLTrainingPersistenceError
from ml_training.models import DatasetType, DatasetVersion
from research_lab.base_repository import PostgresRepositoryBase

logger = logging.getLogger(__name__)

_MODULE = "ml_training.datasets.repository"
_COMPONENT = "ml_training"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ml_training_dataset_versions (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    dataset_type VARCHAR(16) NOT NULL,
    symbols JSONB NOT NULL,
    horizons_days JSONB NOT NULL,
    feature_names JSONB NOT NULL,
    label_names JSONB NOT NULL,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    row_count INTEGER NOT NULL,
    version VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_ml_training_dataset_versions_lookup
    ON ml_training_dataset_versions (dataset_type, created_at DESC);
"""


class DatasetRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, dataset_version: DatasetVersion) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ml_training_dataset_versions
                        (name, dataset_type, symbols, horizons_days, feature_names, label_names,
                         start_at, end_at, row_count, version, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        dataset_version.name, dataset_version.dataset_type.value,
                        json.dumps(dataset_version.symbols), json.dumps(dataset_version.horizons_days),
                        json.dumps(dataset_version.feature_names), json.dumps(dataset_version.label_names),
                        dataset_version.start, dataset_version.end, dataset_version.row_count,
                        dataset_version.version, dataset_version.created_at,
                    ),
                )
                dataset_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at)
            raise MLTrainingPersistenceError(f"failed to save dataset version: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, dataset_id=dataset_id)
        return dataset_id

    def get(self, dataset_id: int) -> Optional[DatasetVersion]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM ml_training_dataset_versions WHERE id = %s", (dataset_id,))
                row = cur.fetchone()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get", exc, started_at)
            raise MLTrainingPersistenceError(f"failed to get dataset version: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "get", started_at)
        return self._row_to_model(row) if row else None

    def list_by_type(self, dataset_type: Optional[DatasetType] = None, limit: int = 50) -> List[DatasetVersion]:
        started_at = time.perf_counter()
        query = "SELECT * FROM ml_training_dataset_versions"
        params: tuple = ()
        if dataset_type is not None:
            query += " WHERE dataset_type = %s"
            params = (dataset_type.value,)
        query += " ORDER BY created_at DESC LIMIT %s"
        params = params + (limit,)

        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_by_type", exc, started_at)
            raise MLTrainingPersistenceError(f"failed to list dataset versions: {exc}") from exc
        self._log_success(_COMPONENT, _MODULE, "list_by_type", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> DatasetVersion:
        return DatasetVersion(
            id=row["id"], name=row["name"], dataset_type=DatasetType(row["dataset_type"]),
            symbols=row["symbols"], horizons_days=row["horizons_days"], feature_names=row["feature_names"],
            label_names=row["label_names"], start=row["start_at"], end=row["end_at"],
            row_count=row["row_count"], version=row["version"], created_at=row["created_at"],
        )
