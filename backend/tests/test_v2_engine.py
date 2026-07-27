"""
Tests for v2/core/engine.py's Sprint 1 Task 8 structured-logging addition.
Not a full characterization suite for TradingEngineV2 (out of scope for
this task) - only proves (a) analyze()'s return value is unchanged by the
new logging code, and (b) it emits exactly one structured, machine-
readable JSON log event with the documented fields.
"""
import json
import logging

import pandas as pd
import pytest

from v2.core.engine import TradingEngineV2
from v2.models.schemas import IndicatorOutput, SignalSide


class FakeIndicator:
    def __init__(self, name: str, score: float, confidence: float, side: SignalSide):
        self.name = name
        self._score = score
        self._confidence = confidence
        self._side = side

    async def calculate(self, data: pd.DataFrame, **kwargs) -> IndicatorOutput:
        return IndicatorOutput(
            indicator_name=self.name, score=self._score,
            confidence=self._confidence, side=self._side,
        )


def _make_ohlcv(rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "Open": [100.0] * rows, "High": [101.0] * rows,
        "Low": [99.0] * rows, "Close": [100.5] * rows,
        "Volume": [1000.0] * rows,
    })


@pytest.mark.asyncio
async def test_analyze_return_value_is_unchanged_by_the_logging_addition(caplog):
    engine = TradingEngineV2([
        FakeIndicator("fake1", score=0.5, confidence=0.8, side=SignalSide.BUY),
    ])
    with caplog.at_level(logging.INFO, logger="v2.core.engine"):
        result = await engine.analyze("BTC-USD", _make_ohlcv())

    assert result.symbol == "BTC-USD"
    assert result.aggregated_score == pytest.approx(0.5)
    assert result.confidence == pytest.approx(0.8)
    assert len(result.signals) == 1


@pytest.mark.asyncio
async def test_analyze_emits_one_structured_log_event(caplog):
    engine = TradingEngineV2([
        FakeIndicator("fake1", score=0.5, confidence=0.8, side=SignalSide.BUY),
    ])
    with caplog.at_level(logging.INFO, logger="v2.core.engine"):
        await engine.analyze("BTC-USD", _make_ohlcv())

    assert len(caplog.records) == 1
    record = json.loads(caplog.records[0].message)
    assert record["component"] == "v2_engine"
    assert record["module"] == "v2.core.engine"
    assert record["operation"] == "analyze"
    assert record["status"] == "success"
    assert record["symbol"] == "BTC-USD"
    assert "execution_time_ms" in record
    assert record["aggregated_score"] == pytest.approx(0.5)
    assert record["confidence"] == pytest.approx(0.8)
    assert "risk_score" in record
