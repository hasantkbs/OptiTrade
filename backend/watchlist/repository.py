"""
OptiTrade Watchlist & Alert Platform — persistence.

Self-contained Postgres access (its own connection pool, not
`research_lab.base_repository.PostgresRepositoryBase`), matching the
convention `feature_store/offline_store.py`, `decision_engine/
repository.py`, `model_serving/rollback.py`, and `portfolio/
repository.py` already independently use - this package sits squarely
on the production side of the research/production boundary (see
`tests/test_research_isolation.py`) and must never depend on
`research_lab`.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Iterator, List, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.config import FeatureStoreConfig
from watchlist.exceptions import WatchlistPersistenceError
from watchlist.models import Alert, AlertCategory, AlertType, Watchlist, WatchlistItem

logger = logging.getLogger(__name__)

_MODULE = "watchlist.repository"
_COMPONENT = "watchlist"

_CREATE_WATCHLISTS_SQL = """
CREATE TABLE IF NOT EXISTS watchlist_watchlists (
    id BIGSERIAL PRIMARY KEY,
    owner VARCHAR(128) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""
_CREATE_WATCHLISTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_watchlist_watchlists_owner ON watchlist_watchlists (owner);
"""

_CREATE_ITEMS_SQL = """
CREATE TABLE IF NOT EXISTS watchlist_items (
    id BIGSERIAL PRIMARY KEY,
    watchlist_id BIGINT NOT NULL REFERENCES watchlist_watchlists (id),
    symbol VARCHAR(32) NOT NULL,
    is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
    folder VARCHAR(128),
    tags JSONB NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    added_at TIMESTAMPTZ NOT NULL,
    UNIQUE (watchlist_id, symbol)
);
"""
_CREATE_ITEMS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_watchlist_items_watchlist ON watchlist_items (watchlist_id);
"""

_CREATE_ALERTS_SQL = """
CREATE TABLE IF NOT EXISTS watchlist_alerts (
    id BIGSERIAL PRIMARY KEY,
    owner VARCHAR(128) NOT NULL,
    watchlist_id BIGINT,
    symbol VARCHAR(32),
    portfolio_id BIGINT,
    category VARCHAR(16) NOT NULL,
    alert_type VARCHAR(32) NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}',
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_state JSONB NOT NULL DEFAULT '{}',
    last_checked_at TIMESTAMPTZ,
    last_triggered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);
"""
_CREATE_ALERTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_watchlist_alerts_owner ON watchlist_alerts (owner);
"""
_CREATE_ALERTS_DUE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_watchlist_alerts_due ON watchlist_alerts (enabled, last_checked_at);
"""

_CREATE_TRIGGER_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS watchlist_alert_trigger_history (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES watchlist_alerts (id),
    triggered_at TIMESTAMPTZ NOT NULL,
    message TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'
);
"""
_CREATE_TRIGGER_HISTORY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_watchlist_alert_trigger_history_lookup
    ON watchlist_alert_trigger_history (alert_id, triggered_at DESC);
"""


class WatchlistRepository:
    def __init__(self, config: Optional[FeatureStoreConfig] = None, minconn: int = 1, maxconn: int = 5) -> None:
        self._config = config or FeatureStoreConfig.from_env()
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn, maxconn, host=self._config.postgres_host, port=self._config.postgres_port,
            dbname=self._config.postgres_db, user=self._config.postgres_user, password=self._config.postgres_password,
        )
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(_CREATE_WATCHLISTS_SQL)
            cur.execute(_CREATE_WATCHLISTS_INDEX_SQL)
            cur.execute(_CREATE_ITEMS_SQL)
            cur.execute(_CREATE_ITEMS_INDEX_SQL)
            cur.execute(_CREATE_ALERTS_SQL)
            cur.execute(_CREATE_ALERTS_INDEX_SQL)
            cur.execute(_CREATE_ALERTS_DUE_INDEX_SQL)
            cur.execute(_CREATE_TRIGGER_HISTORY_SQL)
            cur.execute(_CREATE_TRIGGER_HISTORY_INDEX_SQL)

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    # ── Watchlists ───────────────────────────────────────────────────────

    def save_watchlist(self, watchlist: Watchlist) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO watchlist_watchlists (owner, name, created_at) VALUES (%s, %s, %s) RETURNING id",
                    (watchlist.owner, watchlist.name, watchlist.created_at),
                )
                watchlist_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_watchlist", exc, started_at, owner=watchlist.owner)
            raise WatchlistPersistenceError(f"failed to save watchlist: {exc}") from exc
        self._log_success("save_watchlist", started_at, watchlist_id=watchlist_id)
        return watchlist_id

    def get_watchlist(self, watchlist_id: int) -> Optional[Watchlist]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM watchlist_watchlists WHERE id = %s", (watchlist_id,))
            row = cur.fetchone()
        return self._row_to_watchlist(row) if row else None

    def list_watchlists(self, owner: str) -> List[Watchlist]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM watchlist_watchlists WHERE owner = %s ORDER BY created_at", (owner,))
            rows = cur.fetchall()
        return [self._row_to_watchlist(row) for row in rows]

    def delete_watchlist(self, watchlist_id: int) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM watchlist_items WHERE watchlist_id = %s", (watchlist_id,))
            cur.execute("DELETE FROM watchlist_watchlists WHERE id = %s", (watchlist_id,))

    # ── Watchlist items ──────────────────────────────────────────────────

    def save_item(self, item: WatchlistItem) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO watchlist_items (watchlist_id, symbol, is_favorite, folder, tags, notes, added_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (watchlist_id, symbol) DO UPDATE
                        SET is_favorite = EXCLUDED.is_favorite, folder = EXCLUDED.folder,
                            tags = EXCLUDED.tags, notes = EXCLUDED.notes
                    RETURNING id
                    """,
                    (
                        item.watchlist_id, item.symbol, item.is_favorite, item.folder,
                        json.dumps(item.tags), item.notes, item.added_at,
                    ),
                )
                item_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_item", exc, started_at, watchlist_id=item.watchlist_id, symbol=item.symbol)
            raise WatchlistPersistenceError(f"failed to save watchlist item: {exc}") from exc
        self._log_success("save_item", started_at, item_id=item_id)
        return item_id

    def get_item(self, watchlist_id: int, symbol: str) -> Optional[WatchlistItem]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM watchlist_items WHERE watchlist_id = %s AND symbol = %s",
                (watchlist_id, symbol.upper()),
            )
            row = cur.fetchone()
        return self._row_to_item(row) if row else None

    def list_items(self, watchlist_id: int) -> List[WatchlistItem]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM watchlist_items WHERE watchlist_id = %s ORDER BY added_at", (watchlist_id,))
            rows = cur.fetchall()
        return [self._row_to_item(row) for row in rows]

    def delete_item(self, watchlist_id: int, symbol: str) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM watchlist_items WHERE watchlist_id = %s AND symbol = %s", (watchlist_id, symbol.upper()),
            )

    # ── Alerts ───────────────────────────────────────────────────────────

    def save_alert(self, alert: Alert) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO watchlist_alerts
                        (owner, watchlist_id, symbol, portfolio_id, category, alert_type, parameters,
                         cooldown_minutes, enabled, last_state, last_checked_at, last_triggered_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        alert.owner, alert.watchlist_id, alert.symbol, alert.portfolio_id, alert.category.value,
                        alert.alert_type.value, json.dumps(alert.parameters), alert.cooldown_minutes, alert.enabled,
                        json.dumps(alert.last_state), alert.last_checked_at, alert.last_triggered_at,
                        alert.created_at,
                    ),
                )
                alert_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_alert", exc, started_at, owner=alert.owner)
            raise WatchlistPersistenceError(f"failed to save alert: {exc}") from exc
        self._log_success("save_alert", started_at, alert_id=alert_id)
        return alert_id

    def get_alert(self, alert_id: int) -> Optional[Alert]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM watchlist_alerts WHERE id = %s", (alert_id,))
            row = cur.fetchone()
        return self._row_to_alert(row) if row else None

    def list_alerts(
        self, owner: Optional[str] = None, symbol: Optional[str] = None, enabled_only: bool = False,
        limit: int = 500, offset: int = 0,
    ) -> List[Alert]:
        """`limit`/`offset` page through the matching alerts, ordered by
        `(created_at, id)` for a stable, deterministic page boundary
        (created_at alone ties for alerts created in the same instant,
        which would make OFFSET pagination skip/repeat rows even
        without concurrent writes) - `AlertScheduler.run_scan` uses this
        to rotate through the full enabled-alert set one bounded page
        per call rather than ever loading (or being capped to) only the
        first `limit` alerts that ever existed."""
        query = "SELECT * FROM watchlist_alerts WHERE 1=1"
        params: list = []
        if owner is not None:
            query += " AND owner = %s"
            params.append(owner)
        if symbol is not None:
            query += " AND symbol = %s"
            params.append(symbol.upper())
        if enabled_only:
            query += " AND enabled = TRUE"
        query += " ORDER BY created_at, id LIMIT %s OFFSET %s"
        params.append(limit)
        params.append(offset)

        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
        return [self._row_to_alert(row) for row in rows]

    def count_alerts(self, owner: Optional[str] = None, enabled_only: bool = False) -> int:
        query = "SELECT count(*) FROM watchlist_alerts WHERE 1=1"
        params: list = []
        if owner is not None:
            query += " AND owner = %s"
            params.append(owner)
        if enabled_only:
            query += " AND enabled = TRUE"

        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(query, tuple(params))
            return cur.fetchone()[0]

    def update_alert_state(
        self, alert_id: int, last_state: dict, last_checked_at, last_triggered_at,
    ) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE watchlist_alerts
                SET last_state = %s, last_checked_at = %s, last_triggered_at = %s
                WHERE id = %s
                """,
                (json.dumps(last_state), last_checked_at, last_triggered_at, alert_id),
            )

    def set_alert_enabled(self, alert_id: int, enabled: bool) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE watchlist_alerts SET enabled = %s WHERE id = %s", (enabled, alert_id))

    def delete_alert(self, alert_id: int) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM watchlist_alert_trigger_history WHERE alert_id = %s", (alert_id,))
            cur.execute("DELETE FROM watchlist_alerts WHERE id = %s", (alert_id,))

    # ── Trigger history ──────────────────────────────────────────────────

    def save_trigger(self, alert_id: int, triggered_at, message: str, evidence: dict) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO watchlist_alert_trigger_history (alert_id, triggered_at, message, evidence)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (alert_id, triggered_at, message, json.dumps(evidence)),
            )
            return cur.fetchone()[0]

    def list_triggers(self, alert_id: int, limit: int = 50) -> List[dict]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM watchlist_alert_trigger_history
                WHERE alert_id = %s ORDER BY triggered_at DESC LIMIT %s
                """,
                (alert_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    # ── Internals ────────────────────────────────────────────────────────

    def _log_success(self, operation: str, started_at: float, **extra) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, **extra,
        )

    def _log_error(self, operation: str, exc: Exception, started_at: float, **extra) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_ERROR,
            error_type=type(exc).__name__, execution_time_ms=(time.perf_counter() - started_at) * 1000,
            level=logging.ERROR, **extra,
        )

    @staticmethod
    def _row_to_watchlist(row: dict) -> Watchlist:
        return Watchlist(id=row["id"], owner=row["owner"], name=row["name"], created_at=row["created_at"])

    @staticmethod
    def _row_to_item(row: dict) -> WatchlistItem:
        return WatchlistItem(
            id=row["id"], watchlist_id=row["watchlist_id"], symbol=row["symbol"], is_favorite=row["is_favorite"],
            folder=row["folder"], tags=row["tags"], notes=row["notes"], added_at=row["added_at"],
        )

    @staticmethod
    def _row_to_alert(row: dict) -> Alert:
        return Alert(
            id=row["id"], owner=row["owner"], watchlist_id=row["watchlist_id"], symbol=row["symbol"],
            portfolio_id=row["portfolio_id"], category=AlertCategory(row["category"]),
            alert_type=AlertType(row["alert_type"]), parameters=row["parameters"],
            cooldown_minutes=row["cooldown_minutes"], enabled=row["enabled"], last_state=row["last_state"],
            last_checked_at=row["last_checked_at"], last_triggered_at=row["last_triggered_at"],
            created_at=row["created_at"],
        )

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()
