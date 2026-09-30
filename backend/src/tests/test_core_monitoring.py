"""
Tests for core/monitoring.py::validate_predictions (production audit
MEDIUM #9): each matured prediction is validated with its own
`yfinance` network call, but the whole function used to have only one
try/except wrapped around the entire batch. A single symbol's fetch
failure (rate limit, delisted ticker, network hiccup) aborted the loop
before `conn.commit()` was ever reached - silently discarding every
already-validated prediction in that batch - and the `except` branch
never closed the sqlite connection it had opened, leaking it.

Fixed: each prediction's fetch+update is now isolated in its own
try/except (logged, not silently swallowed), and the connection is
always closed via `finally`, in both the success and failure paths.
"""
import sqlite3

import pytest

import core.monitoring as monitoring


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "monitoring_test.db")
    monkeypatch.setattr(monitoring, "DB_PATH", path)
    monitoring.init_db()
    return path


def _insert_matured_prediction(db_path, symbol, decision_code="BUY", price=100.0):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO predictions
                (symbol, score, decision_code, price_at_prediction, target_date, is_correct, prediction_window_days)
            VALUES (?, 0, ?, ?, datetime('now', '-1 day'), NULL, 5)
            """,
            (symbol, decision_code, price),
        )
        conn.commit()
    finally:
        conn.close()


def _is_correct(db_path, symbol):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT is_correct FROM predictions WHERE symbol = ?", (symbol,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else "MISSING"


class _FakeHistory:
    def __init__(self, close_price):
        import pandas as pd
        self.frame = pd.DataFrame({"Close": [close_price]})


class _FakeTicker:
    def __init__(self, price_by_symbol, failing_symbols):
        self._price_by_symbol = price_by_symbol
        self._failing_symbols = failing_symbols

    def __call__(self, symbol):
        return _FakeTickerInstance(symbol, self._price_by_symbol, self._failing_symbols)


class _FakeTickerInstance:
    def __init__(self, symbol, price_by_symbol, failing_symbols):
        self.symbol = symbol
        self._price_by_symbol = price_by_symbol
        self._failing_symbols = failing_symbols

    def history(self, period):
        import pandas as pd
        if self.symbol in self._failing_symbols:
            raise ConnectionError(f"simulated yfinance failure for {self.symbol}")
        return pd.DataFrame({"Close": [self._price_by_symbol[self.symbol]]})


def test_a_failing_symbol_does_not_abort_validation_of_the_rest(db_path, monkeypatch):
    _insert_matured_prediction(db_path, "GOOD_SYM", decision_code="BUY", price=100.0)
    _insert_matured_prediction(db_path, "BAD_SYM", decision_code="BUY", price=100.0)

    fake_ticker = _FakeTicker(price_by_symbol={"GOOD_SYM": 102.0}, failing_symbols={"BAD_SYM"})
    monkeypatch.setattr(monitoring.yf, "Ticker", fake_ticker)

    validated_count = monitoring.validate_predictions()

    assert validated_count == 1
    assert _is_correct(db_path, "GOOD_SYM") == 1
    # The failing symbol is left untouched (still pending), not lost or corrupted.
    assert _is_correct(db_path, "BAD_SYM") is None


def test_a_failing_symbol_is_logged_not_silently_swallowed(db_path, monkeypatch, caplog):
    _insert_matured_prediction(db_path, "BAD_SYM", decision_code="BUY", price=100.0)
    fake_ticker = _FakeTicker(price_by_symbol={}, failing_symbols={"BAD_SYM"})
    monkeypatch.setattr(monitoring.yf, "Ticker", fake_ticker)

    with caplog.at_level("WARNING", logger="core.monitoring"):
        monitoring.validate_predictions()

    assert any("BAD_SYM" in record.message for record in caplog.records)


def test_connection_is_closed_even_when_a_symbol_fails(db_path, monkeypatch):
    _insert_matured_prediction(db_path, "BAD_SYM", decision_code="BUY", price=100.0)
    fake_ticker = _FakeTicker(price_by_symbol={}, failing_symbols={"BAD_SYM"})
    monkeypatch.setattr(monitoring.yf, "Ticker", fake_ticker)

    opened_connections = []
    real_connect = sqlite3.connect

    def _tracking_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened_connections.append(conn)
        return conn

    monkeypatch.setattr(monitoring.sqlite3, "connect", _tracking_connect)

    monitoring.validate_predictions()

    assert len(opened_connections) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened_connections[0].execute("SELECT 1")


def test_connection_is_closed_on_the_success_path_too(db_path, monkeypatch):
    _insert_matured_prediction(db_path, "GOOD_SYM", decision_code="BUY", price=100.0)
    fake_ticker = _FakeTicker(price_by_symbol={"GOOD_SYM": 102.0}, failing_symbols=set())
    monkeypatch.setattr(monitoring.yf, "Ticker", fake_ticker)

    opened_connections = []
    real_connect = sqlite3.connect

    def _tracking_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened_connections.append(conn)
        return conn

    monkeypatch.setattr(monitoring.sqlite3, "connect", _tracking_connect)

    validated_count = monitoring.validate_predictions()

    assert validated_count == 1
    assert len(opened_connections) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened_connections[0].execute("SELECT 1")


def test_returns_zero_when_nothing_is_matured(db_path):
    assert monitoring.validate_predictions() == 0


def _insert_prediction(db_path, symbol, timestamp_sql_offset, is_correct):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"""
            INSERT INTO predictions
                (symbol, score, decision_code, price_at_prediction, timestamp, target_date, is_correct, prediction_window_days)
            VALUES (?, 0, 'BUY', 100.0, datetime('now', '{timestamp_sql_offset}'), datetime('now', '-1 day'), ?, 5)
            """,
            (symbol, is_correct),
        )
        conn.commit()
    finally:
        conn.close()


def _symbol_still_present(db_path, symbol) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT 1 FROM predictions WHERE symbol = ?", (symbol,)).fetchone()
    finally:
        conn.close()
    return row is not None


def test_purge_deletes_validated_predictions_past_retention(db_path):
    _insert_prediction(db_path, "OLD_VALIDATED", "-400 days", is_correct=1)
    deleted = monitoring.purge_old_predictions(retention_days=365)
    assert deleted == 1
    assert not _symbol_still_present(db_path, "OLD_VALIDATED")


def test_purge_keeps_validated_predictions_within_retention(db_path):
    _insert_prediction(db_path, "RECENT_VALIDATED", "-10 days", is_correct=1)
    deleted = monitoring.purge_old_predictions(retention_days=365)
    assert deleted == 0
    assert _symbol_still_present(db_path, "RECENT_VALIDATED")


def test_purge_never_deletes_pending_predictions_regardless_of_age(db_path):
    """A row with `is_correct IS NULL` is still awaiting
    `validate_predictions()` - old age alone must never make it eligible
    for deletion, since that would silently discard an unresolved
    prediction that a later validation pass would otherwise still catch."""
    _insert_prediction(db_path, "OLD_PENDING", "-400 days", is_correct=None)
    deleted = monitoring.purge_old_predictions(retention_days=365)
    assert deleted == 0
    assert _symbol_still_present(db_path, "OLD_PENDING")


def test_purge_uses_the_configured_default_when_no_argument_given(db_path, monkeypatch):
    monkeypatch.setattr(monitoring, "PREDICTION_RETENTION_DAYS", 30)
    _insert_prediction(db_path, "OLD_ENOUGH_FOR_30_DAY_DEFAULT", "-40 days", is_correct=0)
    deleted = monitoring.purge_old_predictions()
    assert deleted == 1
    assert not _symbol_still_present(db_path, "OLD_ENOUGH_FOR_30_DAY_DEFAULT")
