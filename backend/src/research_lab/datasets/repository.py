"""OptiTrade Research Lab — dataset definition persistence.

Only the *definition* (symbols, feature names, date range, version) is
persisted - never a copy of the actual feature values. The Feature
Store remains the single durable source of truth; a dataset is always
rebuilt on demand from it (see `builder.py`), so there is never a stale
second copy to keep in sync.
"""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import DatasetDefinition

logger = logging.getLogger(__name__)

_MODULE = "research_lab.datasets.repository"
_COMPONENT = "research_lab"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_dataset_definitions (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    symbols JSONB NOT NULL,
    feature_names JSONB NOT NULL,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    version VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_dataset_definitions_name
    ON research_dataset_definitions (name, created_at DESC);
"""


class DatasetRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, definition: DatasetDefinition) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_dataset_definitions
                        (name, symbols, feature_names, start_at, end_at, version, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        definition.name, json.dumps(definition.symbols), json.dumps(definition.feature_names),
                        definition.start, definition.end, definition.version, definition.created_at,
                    ),
                )
                definition_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at)
            raise self._wrap("save dataset definition", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, definition_id=definition_id)
        return definition_id

    def get(self, definition_id: int) -> Optional[DatasetDefinition]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM research_dataset_definitions WHERE id = %s", (definition_id,))
                row = cur.fetchone()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get", exc, started_at)
            raise self._wrap("get dataset definition", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "get", started_at)
        return self._row_to_model(row) if row else None

    def list_all(self, limit: int = 50) -> List[DatasetDefinition]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM research_dataset_definitions ORDER BY created_at DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_all", exc, started_at)
            raise self._wrap("list dataset definitions", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_all", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> DatasetDefinition:
        return DatasetDefinition(
            id=row["id"], name=row["name"], symbols=row["symbols"], feature_names=row["feature_names"],
            start=row["start_at"], end=row["end_at"], version=row["version"], created_at=row["created_at"],
        )
