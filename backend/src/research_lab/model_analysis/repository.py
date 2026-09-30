"""OptiTrade Research Lab — model analysis persistence."""
from __future__ import annotations

import logging
import time
from typing import List

import psycopg2
from psycopg2.extras import RealDictCursor

from learning.models import AccuracyMetrics, RollingWindow
from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import ModelAnalysisResult

logger = logging.getLogger(__name__)

_MODULE = "research_lab.model_analysis.repository"
_COMPONENT = "research_lab"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_model_analysis (
    id BIGSERIAL PRIMARY KEY,
    engine_name VARCHAR(64) NOT NULL,
    engine_version VARCHAR(32) NOT NULL,
    window_name VARCHAR(16) NOT NULL,
    sample_count INTEGER NOT NULL,
    accuracy DOUBLE PRECISION NOT NULL,
    precision_score DOUBLE PRECISION NOT NULL,
    recall_score DOUBLE PRECISION NOT NULL,
    calibration_error DOUBLE PRECISION NOT NULL,
    confidence_reliability DOUBLE PRECISION NOT NULL,
    expected_return_error DOUBLE PRECISION NOT NULL,
    volatility_error DOUBLE PRECISION NOT NULL,
    sharpe_ratio DOUBLE PRECISION NOT NULL,
    sortino_ratio DOUBLE PRECISION NOT NULL,
    max_drawdown DOUBLE PRECISION NOT NULL,
    expected_value DOUBLE PRECISION NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_model_analysis_lookup
    ON research_model_analysis (engine_name, engine_version, window_name, computed_at DESC);
"""


class ModelAnalysisRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL], config=config)

    def save(self, result: ModelAnalysisResult) -> None:
        started_at = time.perf_counter()
        metrics = result.accuracy_metrics
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_model_analysis
                        (engine_name, engine_version, window_name, sample_count, accuracy, precision_score,
                         recall_score, calibration_error, confidence_reliability, expected_return_error,
                         volatility_error, sharpe_ratio, sortino_ratio, max_drawdown, expected_value, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        result.engine_name, result.engine_version, result.window.value, metrics.sample_count,
                        metrics.accuracy, metrics.precision, metrics.recall, metrics.calibration_error,
                        metrics.confidence_reliability, metrics.expected_return_error, metrics.volatility_error,
                        result.sharpe_ratio, result.sortino_ratio, result.max_drawdown, result.expected_value,
                        result.computed_at,
                    ),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save", exc, started_at, engine_name=result.engine_name)
            raise self._wrap("save model analysis", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save", started_at, engine_name=result.engine_name)

    def get_history(
        self, engine_name: str, engine_version: str, window: RollingWindow, limit: int = 10,
    ) -> List[ModelAnalysisResult]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM research_model_analysis
                    WHERE engine_name = %s AND engine_version = %s AND window_name = %s
                    ORDER BY computed_at DESC LIMIT %s
                    """,
                    (engine_name, engine_version, window.value, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get_history", exc, started_at, engine_name=engine_name)
            raise self._wrap("get model analysis history", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "get_history", started_at, row_count=len(rows))
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: dict) -> ModelAnalysisResult:
        accuracy_metrics = AccuracyMetrics(
            engine_name=row["engine_name"], engine_version=row["engine_version"],
            window=RollingWindow(row["window_name"]), sample_count=row["sample_count"],
            accuracy=row["accuracy"], precision=row["precision_score"], recall=row["recall_score"],
            calibration_error=row["calibration_error"], confidence_reliability=row["confidence_reliability"],
            expected_return_error=row["expected_return_error"], volatility_error=row["volatility_error"],
            computed_at=row["computed_at"],
        )
        return ModelAnalysisResult(
            engine_name=row["engine_name"], engine_version=row["engine_version"],
            window=RollingWindow(row["window_name"]), accuracy_metrics=accuracy_metrics,
            sharpe_ratio=row["sharpe_ratio"], sortino_ratio=row["sortino_ratio"],
            max_drawdown=row["max_drawdown"], expected_value=row["expected_value"],
            computed_at=row["computed_at"],
        )
