"""
OptiTrade Analytics & Dashboard Platform — persistence.

Read-only. This package owns no tables of its own - it opens its own
Postgres connection pool (the same physical database every other
package's own repository already independently connects to) and reads
tables owned by other packages: `users_users`, `portfolio_portfolios`,
`watchlist_watchlists`, `watchlist_alerts`, `watchlist_alert_trigger_history`,
`paper_trading_accounts`, `decision_engine_executions`,
`model_serving_rollback_overrides`, and - critically -
`ml_training_model_registry`/`ml_training_runs`/
`ml_training_calibration_results`/`ml_training_optimization_results`/
`research_benchmark_results`/`research_promotion_decisions`.

That last group is why this repository exists at all: `tests/
test_research_isolation.py` forbids importing the `ml_training` or
`research_lab` Python packages from any production directory (the sole
exception being `model_serving`, for serving already-trained models).
Reading their tables via raw SQL - never importing their classes - is
the same "self-contained Postgres access" pattern `model_serving/
rollback.py` already uses, and lets the ML/Research dashboards surface
real registry/training/promotion/benchmark data without creating a new
import-level dependency on either package.

No `CREATE TABLE` statements live here - every table above is created
by the package that owns it; this repository only ever reads.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from core.infra_config import postgres_connect_timeout_seconds
from dashboard.config import DashboardConfig

logger = logging.getLogger(__name__)


class DashboardRepository:
    def __init__(self, config: Optional[DashboardConfig] = None, minconn: int = 1, maxconn: int = 5) -> None:
        self._config = config or DashboardConfig.from_env()
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn, maxconn, host=self._config.postgres_host, port=self._config.postgres_port,
            dbname=self._config.postgres_db, user=self._config.postgres_user, password=self._config.postgres_password,
            connect_timeout=postgres_connect_timeout_seconds(),
        )

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def _fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def _fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def _count(self, query: str, params: tuple = ()) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()[0]

    # ── Overview counts ──────────────────────────────────────────────────

    def count_users(self) -> int:
        return self._count("SELECT count(*) FROM users_users")

    def count_active_users(self) -> int:
        return self._count("SELECT count(*) FROM users_users WHERE is_active = TRUE")

    def count_portfolios(self) -> int:
        return self._count("SELECT count(*) FROM portfolio_portfolios")

    def count_watchlists(self) -> int:
        return self._count("SELECT count(*) FROM watchlist_watchlists")

    def count_alerts(self) -> int:
        return self._count("SELECT count(*) FROM watchlist_alerts")

    def count_paper_accounts(self) -> int:
        return self._count("SELECT count(*) FROM paper_trading_accounts")

    def count_ml_models(self) -> int:
        return self._count("SELECT count(*) FROM ml_training_model_registry")

    def count_learning_samples(self) -> int:
        return self._count("SELECT count(*) FROM learning_samples")

    def count_pending_learning_samples(self) -> int:
        return self._count("SELECT count(*) FROM learning_samples WHERE evaluated = FALSE")

    def get_last_evaluated_at(self) -> Optional[datetime]:
        row = self._fetch_one("SELECT max(evaluated_at) AS last_evaluated_at FROM learning_samples")
        return row["last_evaluated_at"] if row else None

    def list_recent_learning_samples(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._fetch_all("SELECT * FROM learning_samples ORDER BY decided_at DESC LIMIT %s", (limit,))

    # ── ML registry / training / calibration / optimization ─────────────

    def list_registry_entries(self, promotion_state: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if promotion_state is not None:
            return self._fetch_all(
                "SELECT * FROM ml_training_model_registry WHERE promotion_state = %s "
                "ORDER BY training_date DESC LIMIT %s",
                (promotion_state, limit),
            )
        return self._fetch_all("SELECT * FROM ml_training_model_registry ORDER BY training_date DESC LIMIT %s", (limit,))

    def get_registry_entry(self, model_id: str) -> Optional[Dict[str, Any]]:
        return self._fetch_one("SELECT * FROM ml_training_model_registry WHERE model_id = %s", (model_id,))

    def find_active_registry_version(self, engine_name: str, version: str) -> Optional[Dict[str, Any]]:
        return self._fetch_one(
            "SELECT * FROM ml_training_model_registry WHERE engine_name = %s AND version = %s "
            "AND promotion_state = 'active'",
            (engine_name, version),
        )

    def get_active_version_for_engine(self, engine_name: str) -> Optional[str]:
        row = self._fetch_one(
            "SELECT version FROM ml_training_model_registry WHERE engine_name = %s AND promotion_state = 'active' "
            "ORDER BY training_date DESC LIMIT 1",
            (engine_name,),
        )
        return row["version"] if row else None

    def list_training_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._fetch_all("SELECT * FROM ml_training_runs ORDER BY training_date DESC LIMIT %s", (limit,))

    def list_calibration_results(self, model_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if model_id is not None:
            return self._fetch_all(
                "SELECT * FROM ml_training_calibration_results WHERE model_id = %s ORDER BY computed_at DESC LIMIT %s",
                (model_id, limit),
            )
        return self._fetch_all("SELECT * FROM ml_training_calibration_results ORDER BY computed_at DESC LIMIT %s", (limit,))

    def list_optimization_results(self, model_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if model_id is not None:
            return self._fetch_all(
                "SELECT * FROM ml_training_optimization_results WHERE model_id = %s ORDER BY computed_at DESC LIMIT %s",
                (model_id, limit),
            )
        return self._fetch_all("SELECT * FROM ml_training_optimization_results ORDER BY computed_at DESC LIMIT %s", (limit,))

    # ── Research Lab benchmarks / promotion decisions ────────────────────

    def list_benchmark_results(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._fetch_all("SELECT * FROM research_benchmark_results ORDER BY created_at DESC LIMIT %s", (limit,))

    def list_promotion_decisions(self, engine_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if engine_name is not None:
            return self._fetch_all(
                "SELECT * FROM research_promotion_decisions WHERE engine_name = %s ORDER BY decided_at DESC LIMIT %s",
                (engine_name, limit),
            )
        return self._fetch_all("SELECT * FROM research_promotion_decisions ORDER BY decided_at DESC LIMIT %s", (limit,))

    # ── Model Serving rollback overrides ─────────────────────────────────

    def list_rollback_overrides(self) -> List[Dict[str, Any]]:
        return self._fetch_all("SELECT * FROM model_serving_rollback_overrides")

    # ── Decision Engine execution history (cross-symbol) ─────────────────

    def list_recent_decision_executions(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if symbol is not None:
            return self._fetch_all(
                "SELECT * FROM decision_engine_executions WHERE symbol = %s ORDER BY timestamp DESC LIMIT %s",
                (symbol.upper(), limit),
            )
        return self._fetch_all("SELECT * FROM decision_engine_executions ORDER BY timestamp DESC LIMIT %s", (limit,))

    # ── Watchlist alert trigger history ──────────────────────────────────

    def list_alert_triggers(
        self, alert_id: Optional[int] = None, since: Optional[datetime] = None, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM watchlist_alert_trigger_history WHERE 1=1"
        params: List[Any] = []
        if alert_id is not None:
            query += " AND alert_id = %s"
            params.append(alert_id)
        if since is not None:
            query += " AND triggered_at >= %s"
            params.append(since)
        query += " ORDER BY triggered_at DESC LIMIT %s"
        params.append(limit)
        return self._fetch_all(query, tuple(params))

    def count_alert_triggers_since(self, since: datetime) -> int:
        return self._count(
            "SELECT count(*) FROM watchlist_alert_trigger_history WHERE triggered_at >= %s", (since,)
        )

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()
