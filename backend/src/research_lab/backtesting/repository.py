"""OptiTrade Research Lab — backtest result persistence."""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import BacktestMethod, BacktestResult, FoldResult

logger = logging.getLogger(__name__)

_MODULE = "research_lab.backtesting.repository"
_COMPONENT = "research_lab"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_backtest_results (
    id BIGSERIAL PRIMARY KEY,
    experiment_id BIGINT,
    method VARCHAR(24) NOT NULL,
    engine_name VARCHAR(64) NOT NULL,
    engine_version VARCHAR(32) NOT NULL,
    symbol VARCHAR(32),
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    folds JSONB NOT NULL,
    aggregate_sharpe DOUBLE PRECISION NOT NULL,
    aggregate_sortino DOUBLE PRECISION NOT NULL,
    aggregate_max_drawdown DOUBLE PRECISION NOT NULL,
    aggregate_win_rate DOUBLE PRECISION NOT NULL,
    aggregate_expected_value DOUBLE PRECISION NOT NULL,
    sample_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_backtest_results_lookup
    ON research_backtest_results (engine_name, engine_version, method, created_at DESC);
"""


class BacktestRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, result: BacktestResult) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_backtest_results
                        (experiment_id, method, engine_name, engine_version, symbol, window_start, window_end,
                         folds, aggregate_sharpe, aggregate_sortino, aggregate_max_drawdown, aggregate_win_rate,
                         aggregate_expected_value, sample_count, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        result.experiment_id, result.method.value, result.engine_name, result.engine_version,
                        result.symbol, result.window_start, result.window_end,
                        json.dumps([fold.model_dump(mode="json") for fold in result.folds]),
                        result.aggregate_sharpe, result.aggregate_sortino, result.aggregate_max_drawdown,
                        result.aggregate_win_rate, result.aggregate_expected_value, result.sample_count,
                        result.created_at,
                    ),
                )
                result_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at, engine_name=result.engine_name)
            raise self._wrap("save backtest result", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, result_id=result_id)
        return result_id

    def get(self, result_id: int) -> Optional[BacktestResult]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM research_backtest_results WHERE id = %s", (result_id,))
                row = cur.fetchone()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get", exc, started_at)
            raise self._wrap("get backtest result", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "get", started_at)
        return self._row_to_model(row) if row else None

    def list_for_engine(
        self, engine_name: str, engine_version: str, method: Optional[BacktestMethod] = None, limit: int = 20,
    ) -> List[BacktestResult]:
        started_at = time.perf_counter()
        query = "SELECT * FROM research_backtest_results WHERE engine_name = %s AND engine_version = %s"
        params: tuple = (engine_name, engine_version)
        if method is not None:
            query += " AND method = %s"
            params = params + (method.value,)
        query += " ORDER BY created_at DESC LIMIT %s"
        params = params + (limit,)

        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_for_engine", exc, started_at, engine_name=engine_name)
            raise self._wrap("list backtest results", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_for_engine", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    def list_for_experiment(self, experiment_id: int, limit: int = 50) -> List[BacktestResult]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM research_backtest_results
                    WHERE experiment_id = %s ORDER BY created_at DESC LIMIT %s
                    """,
                    (experiment_id, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "list_for_experiment", exc, started_at, experiment_id=experiment_id)
            raise self._wrap("list backtest results for experiment", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "list_for_experiment", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> BacktestResult:
        return BacktestResult(
            id=row["id"], experiment_id=row["experiment_id"], method=BacktestMethod(row["method"]),
            engine_name=row["engine_name"], engine_version=row["engine_version"], symbol=row["symbol"],
            window_start=row["window_start"], window_end=row["window_end"],
            folds=[FoldResult(**fold) for fold in row["folds"]],
            aggregate_sharpe=row["aggregate_sharpe"], aggregate_sortino=row["aggregate_sortino"],
            aggregate_max_drawdown=row["aggregate_max_drawdown"], aggregate_win_rate=row["aggregate_win_rate"],
            aggregate_expected_value=row["aggregate_expected_value"], sample_count=row["sample_count"],
            created_at=row["created_at"],
        )
