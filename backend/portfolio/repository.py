"""
OptiTrade Portfolio Intelligence Platform — persistence.

Self-contained Postgres access (its own connection pool, not
`research_lab.base_repository.PostgresRepositoryBase`), matching the
convention `feature_store/offline_store.py`, `decision_engine/
repository.py`, `learning/persistence.py`, and `model_serving/
rollback.py` already independently use - this package sits squarely on
the production side of the research/production boundary (see
`tests/test_research_isolation.py`) and must never depend on
`research_lab`, even indirectly for a generic connection-pool helper.

Only `Portfolio`, `Transaction`, and `PortfolioSnapshot` are ever
persisted - `Position` is always derived from a portfolio's transaction
history (see `service.py`), never stored as its own mutable row.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator, List, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from core.infra_config import postgres_pool_size_from_env
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.config import FeatureStoreConfig
from portfolio.exceptions import PortfolioNotFoundError, PortfolioPersistenceError
from portfolio.models import Portfolio, PortfolioSnapshot, Transaction, TransactionType

logger = logging.getLogger(__name__)

_MODULE = "portfolio.repository"
_COMPONENT = "portfolio"

_CREATE_PORTFOLIOS_SQL = """
CREATE TABLE IF NOT EXISTS portfolio_portfolios (
    id BIGSERIAL PRIMARY KEY,
    owner VARCHAR(128) NOT NULL,
    name VARCHAR(255) NOT NULL,
    base_currency VARCHAR(8) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""
_CREATE_PORTFOLIOS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_portfolio_portfolios_owner ON portfolio_portfolios (owner);
"""

_CREATE_TRANSACTIONS_SQL = """
CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id BIGINT NOT NULL REFERENCES portfolio_portfolios (id),
    transaction_type VARCHAR(16) NOT NULL,
    symbol VARCHAR(32),
    quantity DOUBLE PRECISION,
    price DOUBLE PRECISION,
    amount DOUBLE PRECISION NOT NULL,
    fee DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    tax DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    currency VARCHAR(8) NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);
"""
_CREATE_TRANSACTIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_portfolio_transactions_lookup
    ON portfolio_transactions (portfolio_id, executed_at);
"""

_CREATE_SNAPSHOTS_SQL = """
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id BIGINT NOT NULL REFERENCES portfolio_portfolios (id),
    as_of TIMESTAMPTZ NOT NULL,
    cash_balance DOUBLE PRECISION NOT NULL,
    positions_value DOUBLE PRECISION NOT NULL,
    total_value DOUBLE PRECISION NOT NULL,
    unrealized_pnl DOUBLE PRECISION NOT NULL,
    realized_pnl DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""
_CREATE_SNAPSHOTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_portfolio_snapshots_lookup
    ON portfolio_snapshots (portfolio_id, as_of DESC);
"""


class PortfolioRepository:
    def __init__(
        self, config: Optional[FeatureStoreConfig] = None,
        minconn: Optional[int] = None, maxconn: Optional[int] = None,
    ) -> None:
        if minconn is None or maxconn is None:
            env_minconn, env_maxconn = postgres_pool_size_from_env("PORTFOLIO", 1, 5)
            minconn = env_minconn if minconn is None else minconn
            maxconn = env_maxconn if maxconn is None else maxconn
        self._config = config or FeatureStoreConfig.from_env()
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn, maxconn, host=self._config.postgres_host, port=self._config.postgres_port,
            dbname=self._config.postgres_db, user=self._config.postgres_user, password=self._config.postgres_password,
        )
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(_CREATE_PORTFOLIOS_SQL)
            cur.execute(_CREATE_PORTFOLIOS_INDEX_SQL)
            cur.execute(_CREATE_TRANSACTIONS_SQL)
            cur.execute(_CREATE_TRANSACTIONS_INDEX_SQL)
            cur.execute(_CREATE_SNAPSHOTS_SQL)
            cur.execute(_CREATE_SNAPSHOTS_INDEX_SQL)

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    @contextmanager
    def locked_portfolio(self, portfolio_id: int) -> Iterator["psycopg2.extensions.connection"]:
        """Opens one connection, starts a transaction, and takes a
        `SELECT ... FOR UPDATE` row lock on `portfolio_id` for the
        duration of the `with` block - any concurrent caller that also
        goes through this method for the SAME portfolio_id blocks until
        the first transaction commits or rolls back. Different
        portfolio_ids never block each other (the lock is per-row, not
        table-wide), so concurrency across portfolios is unaffected.

        Callers must do their read-check-write sequence entirely inside
        the `with` block, using the yielded connection (via
        `list_transactions_locked`/`save_transaction_locked` below) -
        reading through a *different* connection/pool checkout would
        not observe the lock and would defeat the whole point."""
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM portfolio_portfolios WHERE id = %s FOR UPDATE", (portfolio_id,))
                    if cur.fetchone() is None:
                        raise PortfolioNotFoundError(f"no portfolio with id {portfolio_id!r}")
                yield conn
        finally:
            self._pool.putconn(conn)

    def list_transactions_locked(
        self, conn: "psycopg2.extensions.connection", portfolio_id: int, symbol: Optional[str] = None,
    ) -> List[Transaction]:
        """Same query as `list_transactions`, but reused inside an
        already-open, already-locked transaction (see `locked_portfolio`)
        instead of checking out a second, unlocked connection."""
        query = "SELECT * FROM portfolio_transactions WHERE portfolio_id = %s"
        params: tuple = (portfolio_id,)
        if symbol is not None:
            query += " AND symbol = %s"
            params = params + (symbol.upper(),)
        query += " ORDER BY executed_at, id"

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def save_transaction_locked(self, conn: "psycopg2.extensions.connection", transaction: Transaction) -> int:
        """Same insert as `save_transaction`, but reused inside an
        already-open, already-locked transaction (see `locked_portfolio`)
        so the write commits atomically with the read-check it followed."""
        started_at = time.perf_counter()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO portfolio_transactions
                        (portfolio_id, transaction_type, symbol, quantity, price, amount, fee, tax,
                         currency, executed_at, notes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        transaction.portfolio_id, transaction.transaction_type.value, transaction.symbol,
                        transaction.quantity, transaction.price, transaction.amount, transaction.fee,
                        transaction.tax, transaction.currency, transaction.executed_at, transaction.notes,
                        transaction.created_at,
                    ),
                )
                transaction_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_transaction_locked", exc, started_at, portfolio_id=transaction.portfolio_id)
            raise PortfolioPersistenceError(f"failed to save transaction: {exc}") from exc
        self._log_success("save_transaction_locked", started_at, transaction_id=transaction_id)
        return transaction_id

    # ── Portfolios ───────────────────────────────────────────────────────

    def save_portfolio(self, portfolio: Portfolio) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO portfolio_portfolios (owner, name, base_currency, created_at)
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (portfolio.owner, portfolio.name, portfolio.base_currency, portfolio.created_at),
                )
                portfolio_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_portfolio", exc, started_at, owner=portfolio.owner)
            raise PortfolioPersistenceError(f"failed to save portfolio: {exc}") from exc
        self._log_success("save_portfolio", started_at, portfolio_id=portfolio_id)
        return portfolio_id

    def get_portfolio(self, portfolio_id: int) -> Optional[Portfolio]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM portfolio_portfolios WHERE id = %s", (portfolio_id,))
            row = cur.fetchone()
        return self._row_to_portfolio(row) if row else None

    def list_portfolios(self, owner: str) -> List[Portfolio]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM portfolio_portfolios WHERE owner = %s ORDER BY created_at", (owner,))
            rows = cur.fetchall()
        return [self._row_to_portfolio(row) for row in rows]

    # ── Transactions ─────────────────────────────────────────────────────

    def save_transaction(self, transaction: Transaction) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO portfolio_transactions
                        (portfolio_id, transaction_type, symbol, quantity, price, amount, fee, tax,
                         currency, executed_at, notes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        transaction.portfolio_id, transaction.transaction_type.value, transaction.symbol,
                        transaction.quantity, transaction.price, transaction.amount, transaction.fee,
                        transaction.tax, transaction.currency, transaction.executed_at, transaction.notes,
                        transaction.created_at,
                    ),
                )
                transaction_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_transaction", exc, started_at, portfolio_id=transaction.portfolio_id)
            raise PortfolioPersistenceError(f"failed to save transaction: {exc}") from exc
        self._log_success("save_transaction", started_at, transaction_id=transaction_id)
        return transaction_id

    def list_transactions(self, portfolio_id: int, symbol: Optional[str] = None) -> List[Transaction]:
        query = "SELECT * FROM portfolio_transactions WHERE portfolio_id = %s"
        params: tuple = (portfolio_id,)
        if symbol is not None:
            query += " AND symbol = %s"
            params = params + (symbol.upper(),)
        query += " ORDER BY executed_at, id"

        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_transaction(row) for row in rows]

    # ── Snapshots ────────────────────────────────────────────────────────

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO portfolio_snapshots
                        (portfolio_id, as_of, cash_balance, positions_value, total_value,
                         unrealized_pnl, realized_pnl, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        snapshot.portfolio_id, snapshot.as_of, snapshot.cash_balance, snapshot.positions_value,
                        snapshot.total_value, snapshot.unrealized_pnl, snapshot.realized_pnl, snapshot.created_at,
                    ),
                )
                snapshot_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_snapshot", exc, started_at, portfolio_id=snapshot.portfolio_id)
            raise PortfolioPersistenceError(f"failed to save snapshot: {exc}") from exc
        self._log_success("save_snapshot", started_at, snapshot_id=snapshot_id)
        return snapshot_id

    def list_snapshots(self, portfolio_id: int, limit: int = 100) -> List[PortfolioSnapshot]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM portfolio_snapshots WHERE portfolio_id = %s ORDER BY as_of DESC LIMIT %s",
                (portfolio_id, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_snapshot(row) for row in rows]

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
    def _row_to_portfolio(row: dict) -> Portfolio:
        return Portfolio(
            id=row["id"], owner=row["owner"], name=row["name"], base_currency=row["base_currency"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_transaction(row: dict) -> Transaction:
        return Transaction(
            id=row["id"], portfolio_id=row["portfolio_id"], transaction_type=TransactionType(row["transaction_type"]),
            symbol=row["symbol"], quantity=row["quantity"], price=row["price"], amount=row["amount"],
            fee=row["fee"], tax=row["tax"], currency=row["currency"], executed_at=row["executed_at"],
            notes=row["notes"], created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_snapshot(row: dict) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            id=row["id"], portfolio_id=row["portfolio_id"], as_of=row["as_of"], cash_balance=row["cash_balance"],
            positions_value=row["positions_value"], total_value=row["total_value"],
            unrealized_pnl=row["unrealized_pnl"], realized_pnl=row["realized_pnl"], created_at=row["created_at"],
        )

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()
