"""
Unit tests for db/repository.py.

All tests use mock sessions — no real PostgreSQL connection is required.
The database layer is tested for correctness of its no-op contract (db=None)
and for correct session interaction (add, commit, execute).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from db import repository


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_session():
    """Return a mock async session with the methods we use in repository.py."""
    session = MagicMock()
    session.add    = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_row(symbol="AAPL", decision_code="BUY", score=65):
    row = MagicMock()
    row.id                        = uuid.uuid4()
    row.symbol                    = symbol
    row.asset_type                = "stock"
    row.score                     = score
    row.decision_code             = decision_code
    row.confidence_pct            = 72.5
    row.predicted_at              = MagicMock(isoformat=MagicMock(return_value="2026-06-30T12:00:00+00:00"))
    row.actual_price_at_prediction = 185.0
    row.actual_price_1d           = None
    row.actual_price_7d           = None
    row.actual_price_30d          = None
    row.actual_outcome            = None
    row.prediction_accuracy       = None
    row.long_signals              = ["RSI oversold"]
    row.short_signals             = []
    return row


# ── store_prediction ──────────────────────────────────────────────────────────

class TestStorePrediction:
    @pytest.mark.asyncio
    async def test_returns_none_when_db_is_none(self):
        result = await repository.store_prediction(
            None,
            symbol="AAPL", asset_type="stock", score=60, decision_code="BUY",
            confidence_pct=70.0, indicators_json={}, scoring_breakdown_json=[],
            long_signals=[], short_signals=[], actual_price_at_prediction=100.0,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_calls_add_and_commit(self):
        session = _mock_session()
        with patch("db.repository.AnalysisPrediction", autospec=False) as MockModel:
            mock_pred = MagicMock()
            mock_pred.id = uuid.uuid4()
            MockModel.return_value = mock_pred

            result = await repository.store_prediction(
                session,
                symbol="AAPL", asset_type="stock", score=70, decision_code="BUY",
                confidence_pct=80.0, indicators_json={"rsi": 30},
                scoring_breakdown_json=[{"name": "RSI"}],
                long_signals=["RSI oversold"], short_signals=[],
                actual_price_at_prediction=185.5,
            )

        session.add.assert_called_once_with(mock_pred)
        session.commit.assert_awaited_once()
        assert result == str(mock_pred.id)

    @pytest.mark.asyncio
    async def test_symbol_uppercased(self):
        session = _mock_session()
        with patch("db.repository.AnalysisPrediction") as MockModel:
            mock_pred = MagicMock()
            mock_pred.id = uuid.uuid4()
            MockModel.return_value = mock_pred
            await repository.store_prediction(
                session,
                symbol="aapl", asset_type="stock", score=50, decision_code="NEUTRAL",
                confidence_pct=50.0, indicators_json=None, scoring_breakdown_json=None,
                long_signals=None, short_signals=None, actual_price_at_prediction=None,
            )
        call_kwargs = MockModel.call_args[1]
        assert call_kwargs["symbol"] == "AAPL"


# ── get_predictions ───────────────────────────────────────────────────────────

class TestGetPredictions:
    # Note: these tests do NOT patch AnalysisPrediction because select(model)
    # validates its argument. We use the real model and only mock session.execute.

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_db_is_none(self):
        result = await repository.get_predictions(None)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        session = _mock_session()
        rows = [_make_row("AAPL"), _make_row("MSFT")]
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = rows
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=execute_result)

        result = await repository.get_predictions(session, limit=100)

        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[1]["symbol"] == "MSFT"

    @pytest.mark.asyncio
    async def test_dict_keys_complete(self):
        session = _mock_session()
        row = _make_row()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [row]
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=execute_result)

        result = await repository.get_predictions(session)

        expected_keys = {
            "id", "symbol", "asset_type", "score", "decision_code",
            "confidence_pct", "predicted_at", "actual_price_at_prediction",
            "actual_price_1d", "actual_price_7d", "actual_price_30d",
            "actual_outcome", "prediction_accuracy", "long_signals", "short_signals",
        }
        assert set(result[0].keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_rows(self):
        session = _mock_session()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=execute_result)

        result = await repository.get_predictions(session)

        assert result == []


# ── update_prediction_outcome ────────────────────────────────────────────────

class TestUpdatePredictionOutcome:
    @pytest.mark.asyncio
    async def test_returns_false_when_db_is_none(self):
        result = await repository.update_prediction_outcome(
            None,
            prediction_id=str(uuid.uuid4()),
            actual_price=200.0,
            actual_outcome="CORRECT",
            prediction_accuracy=1.0,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        session = _mock_session()
        with patch("db.repository.AnalysisPrediction"), \
             patch("db.repository.update") as mock_update:
            mock_stmt = MagicMock()
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.values.return_value = mock_stmt
            mock_update.return_value = mock_stmt

            result = await repository.update_prediction_outcome(
                session,
                prediction_id=str(uuid.uuid4()),
                actual_price=195.0,
                actual_outcome="CORRECT",
                prediction_accuracy=0.9,
                price_period="1d",
            )

        assert result is True
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_outcome_uppercased(self):
        session = _mock_session()
        pred_id = str(uuid.uuid4())
        with patch("db.repository.AnalysisPrediction"), \
             patch("db.repository.update") as mock_update:
            mock_stmt = MagicMock()
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.values.return_value = mock_stmt
            mock_update.return_value = mock_stmt
            captured_values = {}

            def capture_values(**kwargs):
                captured_values.update(kwargs)
                return mock_stmt

            mock_stmt.values.side_effect = capture_values

            await repository.update_prediction_outcome(
                session,
                prediction_id=pred_id,
                actual_price=100.0,
                actual_outcome="correct",
                prediction_accuracy=0.8,
            )

        assert captured_values.get("actual_outcome") == "CORRECT"


# ── get_prediction_by_id ──────────────────────────────────────────────────────

class TestGetPredictionById:
    # Same as TestGetPredictions: use real model, only mock session.execute.

    @pytest.mark.asyncio
    async def test_returns_none_when_db_is_none(self):
        result = await repository.get_prediction_by_id(None, str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = _mock_session()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)

        result = await repository.get_prediction_by_id(session, str(uuid.uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        session = _mock_session()
        row = _make_row()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = row
        session.execute = AsyncMock(return_value=execute_result)

        result = await repository.get_prediction_by_id(session, str(uuid.uuid4()))

        assert result is not None
        assert result["symbol"] == "AAPL"


# ── store_ohlcv ───────────────────────────────────────────────────────────────

class TestStoreOHLCV:
    @pytest.mark.asyncio
    async def test_returns_zero_when_db_is_none(self):
        result = await repository.store_ohlcv(
            None, symbol="AAPL", rows=[{"time": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1000}]
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_rows_empty(self):
        session = _mock_session()
        result = await repository.store_ohlcv(session, symbol="AAPL", rows=[])
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_row_count(self):
        session = _mock_session()
        rows = [
            {"time": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1000},
            {"time": "2026-01-02", "open": 1.5, "high": 2.5, "low": 1, "close": 2, "volume": 2000},
        ]
        with patch("db.repository.OHLCVData"), \
             patch("db.repository.pg_insert") as mock_insert:
            mock_stmt = MagicMock()
            mock_stmt.values.return_value = mock_stmt
            mock_stmt.on_conflict_do_update.return_value = mock_stmt
            mock_insert.return_value = mock_stmt

            result = await repository.store_ohlcv(session, symbol="AAPL", rows=rows)

        assert result == 2
