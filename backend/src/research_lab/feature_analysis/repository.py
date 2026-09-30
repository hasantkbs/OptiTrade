"""OptiTrade Research Lab — feature analysis persistence."""
from __future__ import annotations

import logging
import time
from typing import List

import psycopg2
from psycopg2.extras import RealDictCursor

from research_lab.base_repository import PostgresRepositoryBase
from research_lab.models import (
    FeatureCorrelationRecord,
    FeatureDriftRecord,
    FeatureImportanceRecord,
    FeatureStabilityRecord,
)

logger = logging.getLogger(__name__)

_MODULE = "research_lab.feature_analysis.repository"
_COMPONENT = "research_lab"

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS research_feature_importance (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    engine_name VARCHAR(64) NOT NULL,
    feature_name VARCHAR(128) NOT NULL,
    importance DOUBLE PRECISION NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS research_feature_correlation (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    feature_a VARCHAR(128) NOT NULL,
    feature_b VARCHAR(128) NOT NULL,
    correlation DOUBLE PRECISION NOT NULL,
    sample_count INTEGER NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS research_feature_stability (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    feature_name VARCHAR(128) NOT NULL,
    stability_score DOUBLE PRECISION NOT NULL,
    coefficient_of_variation DOUBLE PRECISION NOT NULL,
    sample_count INTEGER NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS research_feature_drift (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    feature_name VARCHAR(128) NOT NULL,
    drift_statistic DOUBLE PRECISION NOT NULL,
    p_value DOUBLE PRECISION NOT NULL,
    drifted BOOLEAN NOT NULL,
    baseline_window_start TIMESTAMPTZ NOT NULL,
    baseline_window_end TIMESTAMPTZ NOT NULL,
    recent_window_start TIMESTAMPTZ NOT NULL,
    recent_window_end TIMESTAMPTZ NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS ix_research_feature_importance_lookup
    ON research_feature_importance (symbol, engine_name, feature_name, computed_at DESC);
CREATE INDEX IF NOT EXISTS ix_research_feature_correlation_lookup
    ON research_feature_correlation (symbol, feature_a, feature_b, computed_at DESC);
CREATE INDEX IF NOT EXISTS ix_research_feature_stability_lookup
    ON research_feature_stability (symbol, feature_name, computed_at DESC);
CREATE INDEX IF NOT EXISTS ix_research_feature_drift_lookup
    ON research_feature_drift (symbol, feature_name, computed_at DESC);
"""


class FeatureAnalysisRepository(PostgresRepositoryBase):
    def __init__(self, config=None) -> None:
        super().__init__(schema_statements=[_CREATE_TABLES_SQL, _CREATE_INDEXES_SQL], config=config)

    def save_importance(self, record: FeatureImportanceRecord) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_feature_importance
                        (symbol, engine_name, feature_name, importance, computed_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (record.symbol, record.engine_name, record.feature_name, record.importance, record.computed_at),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save_importance", exc, started_at)
            raise self._wrap("save feature importance", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save_importance", started_at, symbol=record.symbol)

    def get_importance_history(self, symbol: str, engine_name: str, feature_name: str, limit: int = 50) -> List[FeatureImportanceRecord]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM research_feature_importance
                    WHERE symbol = %s AND engine_name = %s AND feature_name = %s
                    ORDER BY computed_at DESC LIMIT %s
                    """,
                    (symbol, engine_name, feature_name, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "get_importance_history", exc, started_at)
            raise self._wrap("get feature importance history", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "get_importance_history", started_at, row_count=len(rows))
        return [
            FeatureImportanceRecord(
                symbol=row["symbol"], engine_name=row["engine_name"], feature_name=row["feature_name"],
                importance=row["importance"], computed_at=row["computed_at"],
            )
            for row in rows
        ]

    def save_correlation(self, record: FeatureCorrelationRecord) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_feature_correlation
                        (symbol, feature_a, feature_b, correlation, sample_count, window_start, window_end, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.symbol, record.feature_a, record.feature_b, record.correlation,
                        record.sample_count, record.window_start, record.window_end, record.computed_at,
                    ),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save_correlation", exc, started_at)
            raise self._wrap("save feature correlation", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save_correlation", started_at, symbol=record.symbol)

    def save_stability(self, record: FeatureStabilityRecord) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_feature_stability
                        (symbol, feature_name, stability_score, coefficient_of_variation, sample_count,
                         window_start, window_end, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.symbol, record.feature_name, record.stability_score, record.coefficient_of_variation,
                        record.sample_count, record.window_start, record.window_end, record.computed_at,
                    ),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save_stability", exc, started_at)
            raise self._wrap("save feature stability", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save_stability", started_at, symbol=record.symbol)

    def save_drift(self, record: FeatureDriftRecord) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_feature_drift
                        (symbol, feature_name, drift_statistic, p_value, drifted,
                         baseline_window_start, baseline_window_end, recent_window_start, recent_window_end,
                         computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.symbol, record.feature_name, record.drift_statistic, record.p_value, record.drifted,
                        record.baseline_window_start, record.baseline_window_end,
                        record.recent_window_start, record.recent_window_end, record.computed_at,
                    ),
                )
        except psycopg2.Error as exc:
            self._log_error(_COMPONENT, _MODULE, "save_drift", exc, started_at)
            raise self._wrap("save feature drift", exc) from exc
        self._log_success(_COMPONENT, _MODULE, "save_drift", started_at, symbol=record.symbol)
