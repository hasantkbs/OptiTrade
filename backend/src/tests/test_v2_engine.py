"""
Tests for v2/core/engine.py: the Sprint 1 Task 8 structured-logging
addition, and the later consolidation making the Decision Engine the
single decision authority for `aggregated_score`/`confidence` (see
docs/architecture/gap-analysis.md section 1's superseded-note) - not a
full characterization suite for TradingEngineV2 beyond that.

A `FakeDecisionEngine` is injected into every test below so none of them
hit the real Decision Engine (Feature Store/Postgres/live engines) -
`TradingEngineV2.analyze()` resolves a real one lazily on first use only
when `decision_engine=None` was passed at construction (see that
module's own comment on why it can't resolve it eagerly in __init__).
"""
import json
import logging
from datetime import datetime

import pandas as pd
import pytest

from decision_engine.models import DecisionOutput, Prediction
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


class FakeDecisionEngine:
    def __init__(self, decision_output: DecisionOutput = None, raises: Exception = None) -> None:
        self._decision_output = decision_output or _make_decision_output()
        self._raises = raises
        self.calls = []

    def decide(self, symbol: str, strict: bool = False) -> DecisionOutput:
        self.calls.append(symbol)
        if self._raises is not None:
            raise self._raises
        return self._decision_output


def _make_decision_output(decision=Prediction.BUY, confidence=0.8) -> DecisionOutput:
    return DecisionOutput(
        symbol="BTC-USD", decision=decision, confidence=confidence,
        expected_return=0.01, expected_volatility=0.02,
        aggregation_strategy_version="test", data_sufficiency=1.0,
        evidence=[], engine_results=[],
    )


def _make_ohlcv(rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "Open": [100.0] * rows, "High": [101.0] * rows,
        "Low": [99.0] * rows, "Close": [100.5] * rows,
        "Volume": [1000.0] * rows,
    })


@pytest.mark.asyncio
async def test_analyze_headline_score_comes_from_the_decision_engine_not_the_indicators():
    """`aggregated_score`/`confidence` are the Decision Engine's - BUY at
    confidence=0.8 encodes to (+0.8, 0.8), deliberately different from
    the lone indicator's own (0.5, 0.8) so the two sources can't be
    confused for one another."""
    decision_engine = FakeDecisionEngine(_make_decision_output(Prediction.BUY, confidence=0.8))
    engine = TradingEngineV2(
        [FakeIndicator("fake1", score=0.5, confidence=0.8, side=SignalSide.BUY)],
        decision_engine=decision_engine,
    )

    result = await engine.analyze("BTC-USD", _make_ohlcv())

    assert decision_engine.calls == ["BTC-USD"]
    assert result.symbol == "BTC-USD"
    assert result.aggregated_score == pytest.approx(0.8)
    assert result.confidence == pytest.approx(0.8)
    # The indicator's own output is still surfaced in `signals` - only
    # the headline score/confidence authority changed.
    assert len(result.signals) == 1
    assert result.signals[0].score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_analyze_sell_decision_yields_a_negative_aggregated_score():
    decision_engine = FakeDecisionEngine(_make_decision_output(Prediction.SELL, confidence=0.6))
    engine = TradingEngineV2([], decision_engine=decision_engine)

    result = await engine.analyze("BTC-USD", _make_ohlcv())

    assert result.aggregated_score == pytest.approx(-0.6)
    assert result.confidence == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_analyze_hold_decision_yields_a_zero_aggregated_score():
    decision_engine = FakeDecisionEngine(_make_decision_output(Prediction.HOLD, confidence=0.4))
    engine = TradingEngineV2([], decision_engine=decision_engine)

    result = await engine.analyze("BTC-USD", _make_ohlcv())

    assert result.aggregated_score == pytest.approx(0.0)
    assert result.confidence == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_analyze_falls_back_to_its_own_fusion_when_the_decision_engine_fails():
    """A Decision Engine failure must not turn into a hard failure for
    this endpoint - falls back to this engine's own indicator fusion
    (the pre-consolidation behavior) instead."""
    decision_engine = FakeDecisionEngine(raises=RuntimeError("feature store unavailable"))
    engine = TradingEngineV2(
        [FakeIndicator("fake1", score=0.5, confidence=0.8, side=SignalSide.BUY)],
        decision_engine=decision_engine,
    )

    result = await engine.analyze("BTC-USD", _make_ohlcv())

    assert result.aggregated_score == pytest.approx(0.5)
    assert result.confidence == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_analyze_falls_back_to_its_own_fusion_when_data_sufficiency_too_low():
    """Finding 3: decide(strict=True) can return normally with very few
    engines voting (data_sufficiency=0.2 means only 1 of 5 voted) - that
    low-confidence-input output must be treated the same as the
    exception-fallback path, not silently override this engine's own
    fusion result."""
    decision_output = _make_decision_output(Prediction.SELL, confidence=0.9)
    decision_output = decision_output.model_copy(update={"data_sufficiency": 0.2})
    decision_engine = FakeDecisionEngine(decision_output)
    engine = TradingEngineV2(
        [FakeIndicator("fake1", score=0.5, confidence=0.8, side=SignalSide.BUY)],
        decision_engine=decision_engine,
    )

    result = await engine.analyze("BTC-USD", _make_ohlcv())

    assert decision_engine.calls == ["BTC-USD"]
    # Not overridden by the low-data_sufficiency SELL output - falls
    # back to the indicator fusion result instead (score=0.5, conf=0.8,
    # same as test_analyze_falls_back_to_its_own_fusion_when_the_
    # decision_engine_fails above).
    assert result.aggregated_score == pytest.approx(0.5)
    assert result.confidence == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_analyze_result_timestamp_is_utc_aware_not_naive():
    """API contract audit: `EngineResult.timestamp` (a plain `str`
    field - see v2/models/schemas.py) must carry an explicit UTC offset
    so a mobile client can parse it unambiguously. Previously built from
    a naive `datetime.now().isoformat()` (server local time, no offset)."""
    engine = TradingEngineV2(
        [FakeIndicator("fake1", score=0.5, confidence=0.8, side=SignalSide.BUY)],
        decision_engine=FakeDecisionEngine(),
    )
    result = await engine.analyze("BTC-USD", _make_ohlcv())

    parsed = datetime.fromisoformat(result.timestamp)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


@pytest.mark.asyncio
async def test_analyze_emits_one_structured_log_event(caplog):
    engine = TradingEngineV2(
        [FakeIndicator("fake1", score=0.5, confidence=0.8, side=SignalSide.BUY)],
        decision_engine=FakeDecisionEngine(_make_decision_output(Prediction.BUY, confidence=0.8)),
    )
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
    assert record["aggregated_score"] == pytest.approx(0.8)
    assert record["confidence"] == pytest.approx(0.8)
    assert "risk_score" in record
