"""OptiTrade Research Lab — promotion decision persistence.

Every row here is a RECOMMENDATION only - see `service.py`'s
docstring. Nothing in this package ever writes to
`engine_registry`/`decision_engine` to actually promote anything.
"""
from __future__ import annotations

import logging
import time
from typing import List

import psycopg2
from psycopg2.extras import RealDictCursor

from learning.models import RollingWindow
from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import PromotionDecision, PromotionRecommendation

logger = logging.getLogger(__name__)

_MODULE = "research_lab.promotion.repository"
_COMPONENT = "research_lab"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_promotion_decisions (
    id BIGSERIAL PRIMARY KEY,
    experiment_id BIGINT,
    engine_name VARCHAR(64) NOT NULL,
    candidate_version VARCHAR(32) NOT NULL,
    live_version VARCHAR(32) NOT NULL,
    recommendation VARCHAR(16) NOT NULL,
    rationale TEXT NOT NULL,
    window_name VARCHAR(16) NOT NULL,
    candidate_accuracy DOUBLE PRECISION NOT NULL,
    live_accuracy DOUBLE PRECISION NOT NULL,
    candidate_sample_count INTEGER NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_promotion_decisions_lookup
    ON research_promotion_decisions (engine_name, candidate_version, decided_at DESC);
"""


class PromotionRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, decision: PromotionDecision) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_promotion_decisions
                        (experiment_id, engine_name, candidate_version, live_version, recommendation, rationale,
                         window_name, candidate_accuracy, live_accuracy, candidate_sample_count, decided_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        decision.experiment_id, decision.engine_name, decision.candidate_version,
                        decision.live_version, decision.recommendation.value, decision.rationale,
                        decision.window.value, decision.candidate_accuracy, decision.live_accuracy,
                        decision.candidate_sample_count, decision.decided_at,
                    ),
                )
                decision_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at, engine_name=decision.engine_name)
            raise self._wrap("save promotion decision", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, decision_id=decision_id)
        return decision_id

    def list_for_engine(self, engine_name: str, candidate_version: str, limit: int = 20) -> List[PromotionDecision]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM research_promotion_decisions
                    WHERE engine_name = %s AND candidate_version = %s
                    ORDER BY decided_at DESC LIMIT %s
                    """,
                    (engine_name, candidate_version, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_for_engine", exc, started_at, engine_name=engine_name)
            raise self._wrap("list promotion decisions", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_for_engine", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> PromotionDecision:
        return PromotionDecision(
            id=row["id"], experiment_id=row["experiment_id"], engine_name=row["engine_name"],
            candidate_version=row["candidate_version"], live_version=row["live_version"],
            recommendation=PromotionRecommendation(row["recommendation"]), rationale=row["rationale"],
            window=RollingWindow(row["window_name"]), candidate_accuracy=row["candidate_accuracy"],
            live_accuracy=row["live_accuracy"], candidate_sample_count=row["candidate_sample_count"],
            decided_at=row["decided_at"],
        )
