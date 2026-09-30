"""OptiTrade Research Lab — Hypothesis Registry persistence."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import Hypothesis, HypothesisOutcome

logger = logging.getLogger(__name__)

_MODULE = "research_lab.hypothesis.repository"
_COMPONENT = "research_lab"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_hypotheses (
    id BIGSERIAL PRIMARY KEY,
    statement TEXT NOT NULL,
    outcome VARCHAR(16),
    evidence JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_hypotheses_outcome
    ON research_hypotheses (outcome, created_at DESC);
"""


class HypothesisRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, hypothesis: Hypothesis) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_hypotheses (statement, outcome, evidence, created_at, resolved_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        hypothesis.statement,
                        hypothesis.outcome.value if hypothesis.outcome else None,
                        json.dumps(hypothesis.evidence),
                        hypothesis.created_at,
                        hypothesis.resolved_at,
                    ),
                )
                hypothesis_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at)
            raise self._wrap("save hypothesis", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, hypothesis_id=hypothesis_id)
        return hypothesis_id

    def get(self, hypothesis_id: int) -> Optional[Hypothesis]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM research_hypotheses WHERE id = %s", (hypothesis_id,))
                row = cur.fetchone()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get", exc, started_at)
            raise self._wrap("get hypothesis", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "get", started_at)
        return self._row_to_model(row) if row else None

    def update_outcome(
        self, hypothesis_id: int, outcome: HypothesisOutcome, evidence: List[str], resolved_at: datetime,
    ) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE research_hypotheses
                    SET outcome = %s, evidence = %s, resolved_at = %s
                    WHERE id = %s
                    """,
                    (outcome.value, json.dumps(evidence), resolved_at, hypothesis_id),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "update_outcome", exc, started_at, hypothesis_id=hypothesis_id)
            raise self._wrap("update hypothesis outcome", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "update_outcome", started_at, hypothesis_id=hypothesis_id)

    def list_by_outcome(self, outcome: Optional[HypothesisOutcome] = None, limit: int = 100) -> List[Hypothesis]:
        started_at = time.perf_counter()
        query = "SELECT * FROM research_hypotheses"
        params: tuple = ()
        if outcome is not None:
            query += " WHERE outcome = %s"
            params = (outcome.value,)
        query += " ORDER BY created_at DESC LIMIT %s"
        params = params + (limit,)

        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_by_outcome", exc, started_at)
            raise self._wrap("list hypotheses", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_by_outcome", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> Hypothesis:
        return Hypothesis(
            id=row["id"], statement=row["statement"],
            outcome=HypothesisOutcome(row["outcome"]) if row["outcome"] else None,
            evidence=row["evidence"], created_at=row["created_at"], resolved_at=row["resolved_at"],
        )
