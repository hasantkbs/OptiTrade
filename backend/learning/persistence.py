"""
OptiTrade Continuous Learning — PostgreSQL persistence.

Uses the same PostgreSQL database as the Feature Store and Decision
Engine (`feature_store.config.FeatureStoreConfig`'s connection
settings), the same `ThreadedConnectionPool` + `_connection()`
contextmanager pattern as `feature_store/offline_store.py` and
`decision_engine/repository.py`, and the same idempotent-schema
convention (`CREATE TABLE IF NOT EXISTS`) - no separate migration
framework.

Five tables:
  - `learning_samples` - one row per tracked decision/shadow vote.
  - `learning_engine_outcomes` - denormalized, one row per engine per
    sample, the unit `accuracy.py`/`weighting.py`/`drift.py` query.
  - `learning_accuracy_metrics` - historical snapshots of computed
    per-engine, per-window accuracy.
  - `learning_weight_updates` - audit trail of every weight change.
  - `learning_drift_signals` - history of drift-detection verdicts.
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterator, List, Optional, Tuple

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from core.infra_config import postgres_pool_size_from_env
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.models import EngineVote
from feature_store.config import FeatureStoreConfig
from learning.exceptions import LearningPersistenceError
from learning.models import (
    AccuracyMetrics,
    DriftSignal,
    DriftType,
    EngineOutcomeRecord,
    LearningSample,
    RollingWindow,
    SampleSource,
    WeightingPolicy,
    WeightUpdate,
)

logger = logging.getLogger(__name__)

# Every one of the five tables above is written continuously and never
# UPDATEd away except to flip `evaluated`/`evaluated_at` - none is
# pruned anywhere else in this codebase. 365 days comfortably exceeds
# the largest `RollingWindow` (`NINETY_DAY`, see learning/models.py)
# any accuracy/weighting/drift computation actually reads. See
# `LearningRepository.purge_old_history()`.
_DEFAULT_HISTORY_RETENTION_DAYS = int(os.getenv("LEARNING_HISTORY_RETENTION_DAYS", "365"))

_CREATE_SAMPLES_SQL = """
CREATE TABLE IF NOT EXISTS learning_samples (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    source VARCHAR(8) NOT NULL,
    decision VARCHAR(8) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    expected_return DOUBLE PRECISION NOT NULL,
    expected_volatility DOUBLE PRECISION NOT NULL,
    engine_results JSONB NOT NULL,
    evidence JSONB NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL,
    evaluation_horizon_days INTEGER NOT NULL,
    evaluated BOOLEAN NOT NULL DEFAULT FALSE,
    evaluated_at TIMESTAMPTZ,
    actual_return DOUBLE PRECISION,
    actual_volatility DOUBLE PRECISION,
    correct BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_CREATE_SAMPLES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_learning_samples_pending
    ON learning_samples (evaluated, decided_at);
CREATE INDEX IF NOT EXISTS ix_learning_samples_symbol
    ON learning_samples (symbol, decided_at DESC);
"""

_CREATE_OUTCOMES_SQL = """
CREATE TABLE IF NOT EXISTS learning_engine_outcomes (
    id BIGSERIAL PRIMARY KEY,
    sample_id BIGINT NOT NULL REFERENCES learning_samples(id) ON DELETE CASCADE,
    engine_name VARCHAR(64) NOT NULL,
    engine_version VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    source VARCHAR(8) NOT NULL,
    prediction VARCHAR(8) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    expected_return DOUBLE PRECISION NOT NULL,
    expected_volatility DOUBLE PRECISION NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL,
    evaluation_horizon_days INTEGER NOT NULL,
    evaluated BOOLEAN NOT NULL DEFAULT FALSE,
    evaluated_at TIMESTAMPTZ,
    actual_return DOUBLE PRECISION,
    actual_volatility DOUBLE PRECISION,
    correct BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_CREATE_OUTCOMES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_learning_engine_outcomes_engine
    ON learning_engine_outcomes (engine_name, engine_version, decided_at DESC);
CREATE INDEX IF NOT EXISTS ix_learning_engine_outcomes_pending
    ON learning_engine_outcomes (evaluated, decided_at);
"""

_CREATE_ACCURACY_SQL = """
CREATE TABLE IF NOT EXISTS learning_accuracy_metrics (
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
    computed_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_ACCURACY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_learning_accuracy_metrics_lookup
    ON learning_accuracy_metrics (engine_name, engine_version, window_name, computed_at DESC);
"""

_CREATE_WEIGHT_UPDATES_SQL = """
CREATE TABLE IF NOT EXISTS learning_weight_updates (
    id BIGSERIAL PRIMARY KEY,
    engine_name VARCHAR(64) NOT NULL,
    engine_version VARCHAR(32) NOT NULL,
    old_weight DOUBLE PRECISION NOT NULL,
    new_weight DOUBLE PRECISION NOT NULL,
    policy VARCHAR(32) NOT NULL,
    reason TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_WEIGHT_UPDATES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_learning_weight_updates_lookup
    ON learning_weight_updates (engine_name, engine_version, computed_at DESC);
"""

_CREATE_DRIFT_SQL = """
CREATE TABLE IF NOT EXISTS learning_drift_signals (
    id BIGSERIAL PRIMARY KEY,
    engine_name VARCHAR(64) NOT NULL,
    engine_version VARCHAR(32) NOT NULL,
    drift_type VARCHAR(16) NOT NULL,
    magnitude DOUBLE PRECISION NOT NULL,
    recent_window VARCHAR(16) NOT NULL,
    baseline_window VARCHAR(16) NOT NULL,
    evidence TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL
);
"""

_CREATE_DRIFT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_learning_drift_signals_lookup
    ON learning_drift_signals (engine_name, engine_version, detected_at DESC);
"""


class LearningRepository:
    """Stores and retrieves every Continuous Learning artifact."""

    def __init__(
        self,
        config: Optional[FeatureStoreConfig] = None,
        minconn: Optional[int] = None,
        maxconn: Optional[int] = None,
    ) -> None:
        if minconn is None or maxconn is None:
            env_minconn, env_maxconn = postgres_pool_size_from_env("LEARNING", 1, 5)
            minconn = env_minconn if minconn is None else minconn
            maxconn = env_maxconn if maxconn is None else maxconn
        self._config = config or FeatureStoreConfig.from_env()
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn,
            maxconn,
            host=self._config.postgres_host,
            port=self._config.postgres_port,
            dbname=self._config.postgres_db,
            user=self._config.postgres_user,
            password=self._config.postgres_password,
        )
        self._init_schema()

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def _init_schema(self) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            for statement in (
                _CREATE_SAMPLES_SQL, _CREATE_SAMPLES_INDEX_SQL,
                _CREATE_OUTCOMES_SQL, _CREATE_OUTCOMES_INDEX_SQL,
                _CREATE_ACCURACY_SQL, _CREATE_ACCURACY_INDEX_SQL,
                _CREATE_WEIGHT_UPDATES_SQL, _CREATE_WEIGHT_UPDATES_INDEX_SQL,
                _CREATE_DRIFT_SQL, _CREATE_DRIFT_INDEX_SQL,
            ):
                cur.execute(statement)

    # ── Samples ──────────────────────────────────────────────────────────

    def save_sample(self, sample: LearningSample) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO learning_samples
                        (symbol, source, decision, confidence, expected_return,
                         expected_volatility, engine_results, evidence, decided_at,
                         evaluation_horizon_days)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        sample.symbol, sample.source.value, sample.decision.value,
                        sample.confidence, sample.expected_return, sample.expected_volatility,
                        json.dumps([vote.model_dump(mode="json") for vote in sample.engine_results]),
                        json.dumps(sample.evidence), sample.decided_at, sample.evaluation_horizon_days,
                    ),
                )
                sample_id = cur.fetchone()[0]

                for vote in sample.engine_results:
                    cur.execute(
                        """
                        INSERT INTO learning_engine_outcomes
                            (sample_id, engine_name, engine_version, symbol, source, prediction,
                             confidence, expected_return, expected_volatility, decided_at,
                             evaluation_horizon_days)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            sample_id, vote.engine_name, vote.engine_version, sample.symbol,
                            sample.source.value, vote.prediction.value, vote.confidence,
                            vote.expected_return, vote.volatility, sample.decided_at,
                            sample.evaluation_horizon_days,
                        ),
                    )
        except psycopg2.Error as exc:
            self._log_error("save_sample", exc, started_at, symbol=sample.symbol)
            raise LearningPersistenceError(f"failed to persist learning sample: {exc}") from exc

        self._log_success("save_sample", started_at, symbol=sample.symbol)
        return sample_id

    def get_pending_samples(self, now: datetime, limit: int = 200) -> List[LearningSample]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM learning_samples
                    WHERE evaluated = FALSE
                      AND decided_at + (evaluation_horizon_days || ' days')::interval <= %s
                    ORDER BY decided_at ASC
                    LIMIT %s
                    """,
                    (now, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error("get_pending_samples", exc, started_at)
            raise LearningPersistenceError(f"failed to query pending samples: {exc}") from exc

        self._log_success("get_pending_samples", started_at, pending_count=len(rows))
        return [self._row_to_sample(row) for row in rows]

    def mark_sample_evaluated(
        self, sample_id: int, actual_return: float, actual_volatility: float,
        correct: bool, evaluated_at: datetime,
    ) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE learning_samples
                    SET evaluated = TRUE, evaluated_at = %s, actual_return = %s,
                        actual_volatility = %s, correct = %s
                    WHERE id = %s
                    """,
                    (evaluated_at, actual_return, actual_volatility, correct, sample_id),
                )
        except psycopg2.Error as exc:
            self._log_error("mark_sample_evaluated", exc, started_at, sample_id=sample_id)
            raise LearningPersistenceError(f"failed to mark sample evaluated: {exc}") from exc
        self._log_success("mark_sample_evaluated", started_at, sample_id=sample_id)

    def mark_engine_outcomes_evaluated(
        self, sample_id: int, actual_return: float, actual_volatility: float,
        per_engine_correct: List[Tuple[str, str, bool]], evaluated_at: datetime,
    ) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                for engine_name, engine_version, correct in per_engine_correct:
                    cur.execute(
                        """
                        UPDATE learning_engine_outcomes
                        SET evaluated = TRUE, evaluated_at = %s, actual_return = %s,
                            actual_volatility = %s, correct = %s
                        WHERE sample_id = %s AND engine_name = %s AND engine_version = %s
                        """,
                        (evaluated_at, actual_return, actual_volatility, correct,
                         sample_id, engine_name, engine_version),
                    )
        except psycopg2.Error as exc:
            self._log_error("mark_engine_outcomes_evaluated", exc, started_at, sample_id=sample_id)
            raise LearningPersistenceError(f"failed to mark engine outcomes evaluated: {exc}") from exc
        self._log_success("mark_engine_outcomes_evaluated", started_at, sample_id=sample_id)

    # ── Engine outcomes ──────────────────────────────────────────────────

    def get_engine_outcomes(
        self, engine_name: str, engine_version: str, since: datetime, only_evaluated: bool = True,
    ) -> List[EngineOutcomeRecord]:
        started_at = time.perf_counter()
        query = """
            SELECT * FROM learning_engine_outcomes
            WHERE engine_name = %s AND engine_version = %s AND decided_at >= %s
        """
        params: list = [engine_name, engine_version, since]
        if only_evaluated:
            query += " AND evaluated = TRUE"
        query += " ORDER BY decided_at DESC"

        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error("get_engine_outcomes", exc, started_at, engine_name=engine_name)
            raise LearningPersistenceError(f"failed to query engine outcomes: {exc}") from exc

        self._log_success("get_engine_outcomes", started_at, engine_name=engine_name, outcome_count=len(rows))
        return [self._row_to_outcome(row) for row in rows]

    def distinct_engines(self) -> List[Tuple[str, str]]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute("SELECT DISTINCT engine_name, engine_version FROM learning_engine_outcomes")
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error("distinct_engines", exc, started_at)
            raise LearningPersistenceError(f"failed to query distinct engines: {exc}") from exc
        self._log_success("distinct_engines", started_at, engine_count=len(rows))
        return [(row[0], row[1]) for row in rows]

    # ── Accuracy metrics ─────────────────────────────────────────────────

    def save_accuracy_metrics(self, metrics: AccuracyMetrics) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO learning_accuracy_metrics
                        (engine_name, engine_version, window_name, sample_count, accuracy,
                         precision_score, recall_score, calibration_error, confidence_reliability,
                         expected_return_error, volatility_error, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        metrics.engine_name, metrics.engine_version, metrics.window.value,
                        metrics.sample_count, metrics.accuracy, metrics.precision, metrics.recall,
                        metrics.calibration_error, metrics.confidence_reliability,
                        metrics.expected_return_error, metrics.volatility_error, metrics.computed_at,
                    ),
                )
        except psycopg2.Error as exc:
            self._log_error("save_accuracy_metrics", exc, started_at, engine_name=metrics.engine_name)
            raise LearningPersistenceError(f"failed to persist accuracy metrics: {exc}") from exc
        self._log_success("save_accuracy_metrics", started_at, engine_name=metrics.engine_name)

    def get_latest_accuracy(
        self, engine_name: str, engine_version: str, window: RollingWindow,
    ) -> Optional[AccuracyMetrics]:
        history = self.get_accuracy_history(engine_name, engine_version, window, limit=1)
        return history[0] if history else None

    def get_accuracy_history(
        self, engine_name: str, engine_version: str, window: RollingWindow, limit: int = 10,
    ) -> List[AccuracyMetrics]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM learning_accuracy_metrics
                    WHERE engine_name = %s AND engine_version = %s AND window_name = %s
                    ORDER BY computed_at DESC
                    LIMIT %s
                    """,
                    (engine_name, engine_version, window.value, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error("get_accuracy_history", exc, started_at, engine_name=engine_name)
            raise LearningPersistenceError(f"failed to query accuracy history: {exc}") from exc
        self._log_success("get_accuracy_history", started_at, engine_name=engine_name, row_count=len(rows))
        return [self._row_to_accuracy_metrics(row) for row in rows]

    def get_latest_accuracy_for_windows(
        self, engine_name: str, engine_version: str, windows: List[RollingWindow],
    ) -> Dict[RollingWindow, AccuracyMetrics]:
        """The same answer as calling `get_latest_accuracy` once per
        window in `windows`, but as a single round trip - callers that
        need every window for one engine (e.g. a dashboard building an
        accuracy-by-window snapshot per engine) would otherwise issue
        one query per window per engine, an O(engines x windows) query
        count. `DISTINCT ON (window_name)` picks the most recent row
        per window in one query, identically to `get_accuracy_history(
        ..., limit=1)` picking the most recent row for a single window."""
        if not windows:
            return {}
        started_at = time.perf_counter()
        window_values = [window.value for window in windows]
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (window_name) *
                    FROM learning_accuracy_metrics
                    WHERE engine_name = %s AND engine_version = %s AND window_name = ANY(%s)
                    ORDER BY window_name, computed_at DESC
                    """,
                    (engine_name, engine_version, window_values),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error("get_latest_accuracy_for_windows", exc, started_at, engine_name=engine_name)
            raise LearningPersistenceError(f"failed to query accuracy for windows: {exc}") from exc
        self._log_success(
            "get_latest_accuracy_for_windows", started_at, engine_name=engine_name, row_count=len(rows),
        )
        metrics = [self._row_to_accuracy_metrics(row) for row in rows]
        return {m.window: m for m in metrics}

    # ── Weight updates ───────────────────────────────────────────────────

    def save_weight_update(self, update: WeightUpdate) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO learning_weight_updates
                        (engine_name, engine_version, old_weight, new_weight, policy, reason, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        update.engine_name, update.engine_version, update.old_weight,
                        update.new_weight, update.policy.value, update.reason, update.computed_at,
                    ),
                )
        except psycopg2.Error as exc:
            self._log_error("save_weight_update", exc, started_at, engine_name=update.engine_name)
            raise LearningPersistenceError(f"failed to persist weight update: {exc}") from exc
        self._log_success("save_weight_update", started_at, engine_name=update.engine_name)

    def get_latest_weight_update(self, engine_name: str, engine_version: str) -> Optional[WeightUpdate]:
        history = self.get_weight_update_history(engine_name, engine_version, limit=1)
        return history[0] if history else None

    def get_weight_update_history(self, engine_name: str, engine_version: str, limit: int = 10) -> List[WeightUpdate]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM learning_weight_updates
                    WHERE engine_name = %s AND engine_version = %s
                    ORDER BY computed_at DESC LIMIT %s
                    """,
                    (engine_name, engine_version, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error("get_weight_update_history", exc, started_at, engine_name=engine_name)
            raise LearningPersistenceError(f"failed to query weight update history: {exc}") from exc
        self._log_success("get_weight_update_history", started_at, engine_name=engine_name, row_count=len(rows))
        return [
            WeightUpdate(
                engine_name=row["engine_name"], engine_version=row["engine_version"],
                old_weight=row["old_weight"], new_weight=row["new_weight"],
                policy=WeightingPolicy(row["policy"]), reason=row["reason"], computed_at=row["computed_at"],
            )
            for row in rows
        ]

    # ── Drift signals ────────────────────────────────────────────────────

    def save_drift_signal(self, signal: DriftSignal) -> None:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO learning_drift_signals
                        (engine_name, engine_version, drift_type, magnitude, recent_window,
                         baseline_window, evidence, detected_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        signal.engine_name, signal.engine_version, signal.drift_type.value,
                        signal.magnitude, signal.recent_window.value, signal.baseline_window.value,
                        signal.evidence, signal.detected_at,
                    ),
                )
        except psycopg2.Error as exc:
            self._log_error("save_drift_signal", exc, started_at, engine_name=signal.engine_name)
            raise LearningPersistenceError(f"failed to persist drift signal: {exc}") from exc
        self._log_success("save_drift_signal", started_at, engine_name=signal.engine_name)

    def get_recent_drift_signals(self, engine_name: str, engine_version: str, limit: int = 10) -> List[DriftSignal]:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM learning_drift_signals
                    WHERE engine_name = %s AND engine_version = %s
                    ORDER BY detected_at DESC LIMIT %s
                    """,
                    (engine_name, engine_version, limit),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:
            self._log_error("get_recent_drift_signals", exc, started_at, engine_name=engine_name)
            raise LearningPersistenceError(f"failed to query drift signals: {exc}") from exc
        self._log_success("get_recent_drift_signals", started_at, engine_name=engine_name, row_count=len(rows))
        return [
            DriftSignal(
                engine_name=row["engine_name"], engine_version=row["engine_version"],
                drift_type=DriftType(row["drift_type"]), magnitude=row["magnitude"],
                recent_window=RollingWindow(row["recent_window"]),
                baseline_window=RollingWindow(row["baseline_window"]),
                evidence=row["evidence"], detected_at=row["detected_at"],
            )
            for row in rows
        ]

    # ── Retention ────────────────────────────────────────────────────────

    def purge_old_history(self, retention_days: Optional[int] = None) -> Dict[str, int]:
        """Deletes rows older than the retention window from all five
        tables. Returns the number of rows deleted per table.

        `learning_samples` only purges rows already marked `evaluated`,
        and only when none of their `learning_engine_outcomes` rows are
        still pending evaluation - `mark_sample_evaluated` and
        `mark_engine_outcomes_evaluated` are two separate writes (not one
        transaction), so a sample can in principle be flagged evaluated
        while one of its per-engine outcome rows is not yet. Deleting such
        a sample would `ON DELETE CASCADE` its still-pending outcome row.
        `learning_engine_outcomes` itself is never purged directly - every
        outcome row disappears via that cascade when its parent sample is
        purged, so it is never orphaned from (or purged ahead of) its
        sample. `learning_accuracy_metrics`, `learning_weight_updates`,
        and `learning_drift_signals` are pure historical snapshots with no
        pending state, so they purge by age alone."""
        retention_days = retention_days if retention_days is not None else _DEFAULT_HISTORY_RETENTION_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        started_at = time.perf_counter()
        deleted: Dict[str, int] = {}
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM learning_samples
                    WHERE evaluated = TRUE
                      AND decided_at < %s
                      AND id NOT IN (SELECT sample_id FROM learning_engine_outcomes WHERE evaluated = FALSE)
                    """,
                    (cutoff,),
                )
                deleted["learning_samples"] = cur.rowcount

                cur.execute("DELETE FROM learning_accuracy_metrics WHERE computed_at < %s", (cutoff,))
                deleted["learning_accuracy_metrics"] = cur.rowcount

                cur.execute("DELETE FROM learning_weight_updates WHERE computed_at < %s", (cutoff,))
                deleted["learning_weight_updates"] = cur.rowcount

                cur.execute("DELETE FROM learning_drift_signals WHERE detected_at < %s", (cutoff,))
                deleted["learning_drift_signals"] = cur.rowcount
        except psycopg2.Error as exc:
            self._log_error("purge_old_history", exc, started_at)
            raise LearningPersistenceError(f"failed to purge learning history: {exc}") from exc
        self._log_success("purge_old_history", started_at, retention_days=retention_days, **deleted)
        return deleted

    # ── Misc ─────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()

    # ── Row mapping helpers ──────────────────────────────────────────────

    @staticmethod
    def _row_to_sample(row: dict) -> LearningSample:
        return LearningSample(
            id=row["id"], symbol=row["symbol"], source=SampleSource(row["source"]),
            decision=row["decision"], confidence=row["confidence"], expected_return=row["expected_return"],
            expected_volatility=row["expected_volatility"],
            engine_results=[EngineVote(**vote) for vote in row["engine_results"]],
            evidence=row["evidence"], decided_at=row["decided_at"],
            evaluation_horizon_days=row["evaluation_horizon_days"], evaluated=row["evaluated"],
            evaluated_at=row["evaluated_at"], actual_return=row["actual_return"],
            actual_volatility=row["actual_volatility"], correct=row["correct"],
        )

    @staticmethod
    def _row_to_outcome(row: dict) -> EngineOutcomeRecord:
        return EngineOutcomeRecord(
            id=row["id"], sample_id=row["sample_id"], engine_name=row["engine_name"],
            engine_version=row["engine_version"], symbol=row["symbol"], source=SampleSource(row["source"]),
            prediction=row["prediction"], confidence=row["confidence"], expected_return=row["expected_return"],
            expected_volatility=row["expected_volatility"], decided_at=row["decided_at"],
            evaluation_horizon_days=row["evaluation_horizon_days"], evaluated=row["evaluated"],
            evaluated_at=row["evaluated_at"], actual_return=row["actual_return"],
            actual_volatility=row["actual_volatility"], correct=row["correct"],
        )

    @staticmethod
    def _row_to_accuracy_metrics(row: dict) -> AccuracyMetrics:
        return AccuracyMetrics(
            engine_name=row["engine_name"], engine_version=row["engine_version"],
            window=RollingWindow(row["window_name"]), sample_count=row["sample_count"],
            accuracy=row["accuracy"], precision=row["precision_score"], recall=row["recall_score"],
            calibration_error=row["calibration_error"], confidence_reliability=row["confidence_reliability"],
            expected_return_error=row["expected_return_error"], volatility_error=row["volatility_error"],
            computed_at=row["computed_at"],
        )

    @staticmethod
    def _log_success(operation: str, started_at: float, **extra) -> None:
        log_event(
            logger, component="learning", module="learning.persistence", operation=operation,
            status=STATUS_SUCCESS, execution_time_ms=(time.perf_counter() - started_at) * 1000, **extra,
        )

    @staticmethod
    def _log_error(operation: str, exc: Exception, started_at: float, **extra) -> None:
        log_event(
            logger, component="learning", module="learning.persistence", operation=operation,
            status=STATUS_ERROR, error_type=type(exc).__name__,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, level=logging.ERROR, **extra,
        )
