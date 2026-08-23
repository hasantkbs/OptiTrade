"""
OptiTrade Paper Trading & Trade Journal Platform — persistence.

Self-contained Postgres access (its own connection pool), matching the
convention `users/repository.py`, `portfolio/repository.py`, and
`watchlist/repository.py` already independently use.
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

from core.infra_config import postgres_pool_size_from_env
from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.models import Prediction
from paper_trading.config import PaperTradingConfig
from paper_trading.exceptions import PaperTradingPersistenceError
from paper_trading.models import (
    EngineVoteSnapshot,
    Fill,
    MarketRegime,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    ScreenshotMetadata,
    TradeJournalEntry,
)

logger = logging.getLogger(__name__)

_MODULE = "paper_trading.repository"
_COMPONENT = "paper_trading"

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS paper_trading_accounts (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        portfolio_id BIGINT NOT NULL,
        name VARCHAR(255) NOT NULL,
        starting_balance DOUBLE PRECISION NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_paper_trading_accounts_user ON paper_trading_accounts (user_id);",
    """
    CREATE TABLE IF NOT EXISTS paper_trading_orders (
        id BIGSERIAL PRIMARY KEY,
        account_id BIGINT NOT NULL REFERENCES paper_trading_accounts (id),
        symbol VARCHAR(32) NOT NULL,
        side VARCHAR(8) NOT NULL,
        order_type VARCHAR(16) NOT NULL,
        quantity DOUBLE PRECISION NOT NULL,
        limit_price DOUBLE PRECISION,
        stop_price DOUBLE PRECISION,
        status VARCHAR(20) NOT NULL,
        filled_quantity DOUBLE PRECISION NOT NULL DEFAULT 0,
        average_fill_price DOUBLE PRECISION,
        commission_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
        tax_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        cancelled_at TIMESTAMPTZ,
        rejection_reason VARCHAR(255),
        notes TEXT NOT NULL DEFAULT ''
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_paper_trading_orders_account ON paper_trading_orders (account_id);",
    "CREATE INDEX IF NOT EXISTS ix_paper_trading_orders_status ON paper_trading_orders (account_id, status);",
    "CREATE INDEX IF NOT EXISTS ix_paper_trading_orders_symbol ON paper_trading_orders (symbol);",
    """
    CREATE TABLE IF NOT EXISTS paper_trading_fills (
        id BIGSERIAL PRIMARY KEY,
        order_id BIGINT NOT NULL REFERENCES paper_trading_orders (id),
        account_id BIGINT NOT NULL REFERENCES paper_trading_accounts (id),
        symbol VARCHAR(32) NOT NULL,
        side VARCHAR(8) NOT NULL,
        quantity DOUBLE PRECISION NOT NULL,
        price DOUBLE PRECISION NOT NULL,
        slippage DOUBLE PRECISION NOT NULL DEFAULT 0,
        spread_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
        commission DOUBLE PRECISION NOT NULL DEFAULT 0,
        tax DOUBLE PRECISION NOT NULL DEFAULT 0,
        executed_at TIMESTAMPTZ NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_paper_trading_fills_order ON paper_trading_fills (order_id);",
    "CREATE INDEX IF NOT EXISTS ix_paper_trading_fills_account_symbol ON paper_trading_fills (account_id, symbol, executed_at);",
    """
    CREATE TABLE IF NOT EXISTS paper_trading_journal_entries (
        id BIGSERIAL PRIMARY KEY,
        order_id BIGINT NOT NULL UNIQUE REFERENCES paper_trading_orders (id),
        account_id BIGINT NOT NULL REFERENCES paper_trading_accounts (id),
        symbol VARCHAR(32) NOT NULL,
        decision VARCHAR(8),
        confidence DOUBLE PRECISION,
        expected_return DOUBLE PRECISION,
        expected_volatility DOUBLE PRECISION,
        risk_level VARCHAR(32),
        data_sufficiency DOUBLE PRECISION,
        evidence JSONB NOT NULL,
        engine_votes JSONB NOT NULL,
        explanation_text TEXT NOT NULL DEFAULT '',
        market_regime VARCHAR(32) NOT NULL,
        feature_snapshot JSONB NOT NULL,
        notes TEXT NOT NULL DEFAULT '',
        tags JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_paper_trading_journal_account ON paper_trading_journal_entries (account_id);",
    """
    CREATE TABLE IF NOT EXISTS paper_trading_screenshots (
        id BIGSERIAL PRIMARY KEY,
        journal_entry_id BIGINT NOT NULL REFERENCES paper_trading_journal_entries (id),
        url TEXT NOT NULL,
        caption TEXT NOT NULL DEFAULT '',
        uploaded_at TIMESTAMPTZ NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_paper_trading_screenshots_entry ON paper_trading_screenshots (journal_entry_id);",
]


class PaperTradingRepository:
    def __init__(
        self, config: Optional[PaperTradingConfig] = None,
        minconn: Optional[int] = None, maxconn: Optional[int] = None,
    ) -> None:
        if minconn is None or maxconn is None:
            env_minconn, env_maxconn = postgres_pool_size_from_env("PAPER_TRADING", 1, 5)
            minconn = env_minconn if minconn is None else minconn
            maxconn = env_maxconn if maxconn is None else maxconn
        self._config = config or PaperTradingConfig.from_env()
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn, maxconn, host=self._config.postgres_host, port=self._config.postgres_port,
            dbname=self._config.postgres_db, user=self._config.postgres_user, password=self._config.postgres_password,
        )
        with self._connection() as conn, conn, conn.cursor() as cur:
            for statement in _SCHEMA_STATEMENTS:
                cur.execute(statement)

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    # ── Accounts ─────────────────────────────────────────────────────────

    def save_account(self, account: PaperAccount) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO paper_trading_accounts (user_id, portfolio_id, name, starting_balance, created_at)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                    """,
                    (account.user_id, account.portfolio_id, account.name, account.starting_balance, account.created_at),
                )
                account_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_account", exc, started_at, user_id=account.user_id)
            raise PaperTradingPersistenceError(f"failed to save paper account: {exc}") from exc
        self._log_success("save_account", started_at, account_id=account_id)
        return account_id

    def get_account(self, account_id: int) -> Optional[PaperAccount]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM paper_trading_accounts WHERE id = %s", (account_id,))
            row = cur.fetchone()
        return self._row_to_account(row) if row else None

    def list_accounts(self, user_id: int) -> List[PaperAccount]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM paper_trading_accounts WHERE user_id = %s ORDER BY created_at", (user_id,))
            rows = cur.fetchall()
        return [self._row_to_account(row) for row in rows]

    # ── Orders ───────────────────────────────────────────────────────────

    def save_order(self, order: Order) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO paper_trading_orders
                    (account_id, symbol, side, order_type, quantity, limit_price, stop_price, status,
                     filled_quantity, average_fill_price, commission_paid, tax_paid, created_at, updated_at,
                     cancelled_at, rejection_reason, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    order.account_id, order.symbol, order.side.value, order.order_type.value, order.quantity,
                    order.limit_price, order.stop_price, order.status.value, order.filled_quantity,
                    order.average_fill_price, order.commission_paid, order.tax_paid, order.created_at,
                    order.updated_at, order.cancelled_at, order.rejection_reason, order.notes,
                ),
            )
            return cur.fetchone()[0]

    def get_order(self, order_id: int) -> Optional[Order]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM paper_trading_orders WHERE id = %s", (order_id,))
            row = cur.fetchone()
        return self._row_to_order(row) if row else None

    def list_orders(self, account_id: int, status: Optional[OrderStatus] = None) -> List[Order]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status is not None:
                cur.execute(
                    "SELECT * FROM paper_trading_orders WHERE account_id = %s AND status = %s ORDER BY created_at DESC",
                    (account_id, status.value),
                )
            else:
                cur.execute(
                    "SELECT * FROM paper_trading_orders WHERE account_id = %s ORDER BY created_at DESC", (account_id,),
                )
            rows = cur.fetchall()
        return [self._row_to_order(row) for row in rows]

    def list_open_orders(self) -> List[Order]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM paper_trading_orders WHERE status IN ('pending', 'partially_filled') "
                "ORDER BY created_at"
            )
            rows = cur.fetchall()
        return [self._row_to_order(row) for row in rows]

    def update_order(self, order: Order) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE paper_trading_orders
                SET quantity = %s, limit_price = %s, stop_price = %s, status = %s, filled_quantity = %s,
                    average_fill_price = %s, commission_paid = %s, tax_paid = %s, updated_at = %s,
                    cancelled_at = %s, rejection_reason = %s, notes = %s
                WHERE id = %s
                """,
                (
                    order.quantity, order.limit_price, order.stop_price, order.status.value, order.filled_quantity,
                    order.average_fill_price, order.commission_paid, order.tax_paid, order.updated_at,
                    order.cancelled_at, order.rejection_reason, order.notes, order.id,
                ),
            )

    # ── Fills ────────────────────────────────────────────────────────────

    def save_fill(self, fill: Fill) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO paper_trading_fills
                    (order_id, account_id, symbol, side, quantity, price, slippage, spread_cost, commission,
                     tax, executed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    fill.order_id, fill.account_id, fill.symbol, fill.side.value, fill.quantity, fill.price,
                    fill.slippage, fill.spread_cost, fill.commission, fill.tax, fill.executed_at,
                ),
            )
            return cur.fetchone()[0]

    def list_fills(self, account_id: int, symbol: Optional[str] = None) -> List[Fill]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            if symbol is not None:
                cur.execute(
                    "SELECT * FROM paper_trading_fills WHERE account_id = %s AND symbol = %s ORDER BY executed_at",
                    (account_id, symbol.upper()),
                )
            else:
                cur.execute(
                    "SELECT * FROM paper_trading_fills WHERE account_id = %s ORDER BY executed_at", (account_id,),
                )
            rows = cur.fetchall()
        return [self._row_to_fill(row) for row in rows]

    def list_fills_for_order(self, order_id: int) -> List[Fill]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM paper_trading_fills WHERE order_id = %s ORDER BY executed_at", (order_id,))
            rows = cur.fetchall()
        return [self._row_to_fill(row) for row in rows]

    # ── Trade journal ────────────────────────────────────────────────────

    def save_journal_entry(self, entry: TradeJournalEntry) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO paper_trading_journal_entries
                    (order_id, account_id, symbol, decision, confidence, expected_return, expected_volatility,
                     risk_level, data_sufficiency, evidence, engine_votes, explanation_text, market_regime,
                     feature_snapshot, notes, tags, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    entry.order_id, entry.account_id, entry.symbol, entry.decision.value if entry.decision else None,
                    entry.confidence, entry.expected_return, entry.expected_volatility, entry.risk_level,
                    entry.data_sufficiency, json.dumps(entry.evidence),
                    json.dumps([vote.model_dump() for vote in entry.engine_votes]), entry.explanation_text,
                    entry.market_regime.value, json.dumps(entry.feature_snapshot), entry.notes,
                    json.dumps(entry.tags), entry.created_at, entry.updated_at,
                ),
            )
            return cur.fetchone()[0]

    def get_journal_entry(self, entry_id: int) -> Optional[TradeJournalEntry]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM paper_trading_journal_entries WHERE id = %s", (entry_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_journal_entry(row, self.list_screenshots(row["id"]))

    def get_journal_entry_by_order(self, order_id: int) -> Optional[TradeJournalEntry]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM paper_trading_journal_entries WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_journal_entry(row, self.list_screenshots(row["id"]))

    def list_journal_entries(self, account_id: int) -> List[TradeJournalEntry]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM paper_trading_journal_entries WHERE account_id = %s ORDER BY created_at DESC",
                (account_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_journal_entry(row, self.list_screenshots(row["id"])) for row in rows]

    def update_journal_entry(self, entry: TradeJournalEntry) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE paper_trading_journal_entries
                SET notes = %s, tags = %s, updated_at = %s
                WHERE id = %s
                """,
                (entry.notes, json.dumps(entry.tags), entry.updated_at, entry.id),
            )

    def save_screenshot(self, screenshot: ScreenshotMetadata) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO paper_trading_screenshots (journal_entry_id, url, caption, uploaded_at)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (screenshot.journal_entry_id, screenshot.url, screenshot.caption, screenshot.uploaded_at),
            )
            return cur.fetchone()[0]

    def list_screenshots(self, journal_entry_id: int) -> List[ScreenshotMetadata]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM paper_trading_screenshots WHERE journal_entry_id = %s ORDER BY uploaded_at",
                (journal_entry_id,),
            )
            rows = cur.fetchall()
        return [
            ScreenshotMetadata(
                id=row["id"], journal_entry_id=row["journal_entry_id"], url=row["url"], caption=row["caption"],
                uploaded_at=row["uploaded_at"],
            )
            for row in rows
        ]

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
    def _row_to_account(row: dict) -> PaperAccount:
        return PaperAccount(
            id=row["id"], user_id=row["user_id"], portfolio_id=row["portfolio_id"], name=row["name"],
            starting_balance=row["starting_balance"], created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_order(row: dict) -> Order:
        return Order(
            id=row["id"], account_id=row["account_id"], symbol=row["symbol"], side=OrderSide(row["side"]),
            order_type=OrderType(row["order_type"]), quantity=row["quantity"], limit_price=row["limit_price"],
            stop_price=row["stop_price"], status=OrderStatus(row["status"]), filled_quantity=row["filled_quantity"],
            average_fill_price=row["average_fill_price"], commission_paid=row["commission_paid"],
            tax_paid=row["tax_paid"], created_at=row["created_at"], updated_at=row["updated_at"],
            cancelled_at=row["cancelled_at"], rejection_reason=row["rejection_reason"], notes=row["notes"],
        )

    @staticmethod
    def _row_to_fill(row: dict) -> Fill:
        return Fill(
            id=row["id"], order_id=row["order_id"], account_id=row["account_id"], symbol=row["symbol"],
            side=OrderSide(row["side"]), quantity=row["quantity"], price=row["price"], slippage=row["slippage"],
            spread_cost=row["spread_cost"], commission=row["commission"], tax=row["tax"],
            executed_at=row["executed_at"],
        )

    @staticmethod
    def _row_to_journal_entry(row: dict, screenshots: List[ScreenshotMetadata]) -> TradeJournalEntry:
        return TradeJournalEntry(
            id=row["id"], order_id=row["order_id"], account_id=row["account_id"], symbol=row["symbol"],
            decision=Prediction(row["decision"]) if row["decision"] else None, confidence=row["confidence"],
            expected_return=row["expected_return"], expected_volatility=row["expected_volatility"],
            risk_level=row["risk_level"], data_sufficiency=row["data_sufficiency"], evidence=row["evidence"],
            engine_votes=[EngineVoteSnapshot(**vote) for vote in row["engine_votes"]],
            explanation_text=row["explanation_text"], market_regime=MarketRegime(row["market_regime"]),
            feature_snapshot=row["feature_snapshot"], notes=row["notes"], tags=row["tags"],
            screenshots=screenshots, created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()
