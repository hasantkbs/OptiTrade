"""OptiTrade Research Lab — report persistence."""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import Report, ReportType

logger = logging.getLogger(__name__)

_MODULE = "research_lab.reports.repository"
_COMPONENT = "research_lab"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_reports (
    id BIGSERIAL PRIMARY KEY,
    report_type VARCHAR(24) NOT NULL,
    title VARCHAR(255) NOT NULL,
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    content JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_reports_lookup
    ON research_reports (report_type, generated_at DESC);
"""


class ReportRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, report: Report) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_reports (report_type, title, period_start, period_end, content, generated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        report.report_type.value, report.title, report.period_start, report.period_end,
                        json.dumps(report.content, default=str), report.generated_at,
                    ),
                )
                report_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at)
            raise self._wrap("save report", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, report_id=report_id)
        return report_id

    def get(self, report_id: int) -> Optional[Report]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM research_reports WHERE id = %s", (report_id,))
                row = cur.fetchone()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get", exc, started_at)
            raise self._wrap("get report", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "get", started_at)
        return self._row_to_model(row) if row else None

    def list_by_type(self, report_type: Optional[ReportType] = None, limit: int = 20) -> List[Report]:
        started_at = time.perf_counter()
        query = "SELECT * FROM research_reports"
        params: tuple = ()
        if report_type is not None:
            query += " WHERE report_type = %s"
            params = (report_type.value,)
        query += " ORDER BY generated_at DESC LIMIT %s"
        params = params + (limit,)

        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_by_type", exc, started_at)
            raise self._wrap("list reports", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_by_type", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> Report:
        return Report(
            id=row["id"], report_type=ReportType(row["report_type"]), title=row["title"],
            period_start=row["period_start"], period_end=row["period_end"],
            content=row["content"], generated_at=row["generated_at"],
        )
