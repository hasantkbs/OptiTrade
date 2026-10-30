"""Unit tests for pipeline/models.py's ChartAISignal and
PipelineResponse.chart_ai - no network, no database, pure model
construction. The full end-to-end population of this field (a real
chart-AI prediction attached to a real /quant/analyze response) is
covered by tests/test_main_quant_endpoint.py instead."""
import pytest
from pydantic import ValidationError

from pipeline.models import ChartAISignal, PipelineMetadata, PipelineResponse, RiskAssessment


def _response(**overrides) -> PipelineResponse:
    defaults = dict(
        symbol="AAPL", decision="BUY", confidence=0.7, expected_return=0.02, expected_volatility=0.1,
        risk=RiskAssessment(risk_level="LOW", expected_volatility=0.1, data_sufficiency=0.9),
        explanation="test",
        metadata=PipelineMetadata(
            pipeline_version="1.0.0", total_duration_ms=1.0,
            engines_available=3, engines_succeeded=3, degraded=False,
        ),
    )
    defaults.update(overrides)
    return PipelineResponse(**defaults)


def test_chart_ai_defaults_to_none():
    assert _response().chart_ai is None


def test_chart_ai_accepts_a_valid_signal():
    response = _response(chart_ai=ChartAISignal(signal="SELL", confidence=0.8))
    assert response.chart_ai.signal == "SELL"
    assert response.chart_ai.confidence == 0.8


def test_chart_ai_confidence_must_be_between_zero_and_one():
    with pytest.raises(ValidationError):
        ChartAISignal(signal="BUY", confidence=1.5)


def test_chart_ai_signal_can_be_set_after_construction():
    """main.py's enrichment helper (Task 2) sets this as a post-
    construction mutation, not at __init__ time - PipelineResponse
    must not be a frozen/immutable model."""
    response = _response()
    response.chart_ai = ChartAISignal(signal="NEUTRAL", confidence=0.5)
    assert response.chart_ai.signal == "NEUTRAL"
