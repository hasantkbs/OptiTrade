"""Tests for engines/fundamental/models.py."""
import pytest
from pydantic import ValidationError

from decision_engine.models import Prediction
from engines.fundamental.models import AnalyzerResult, FundamentalAnalysisResult, FundamentalExecutionMetadata


def test_analyzer_result_defaults():
    result = AnalyzerResult(analyzer_name="valuation", signal=0.5, confidence=0.6)
    assert result.evidence == []
    assert result.features_used == []


@pytest.mark.parametrize("signal", [-1.1, 1.1])
def test_analyzer_result_signal_out_of_range_rejected(signal):
    with pytest.raises(ValidationError):
        AnalyzerResult(analyzer_name="valuation", signal=signal, confidence=0.5)


def test_analyzer_result_rejects_blank_name():
    with pytest.raises(ValidationError):
        AnalyzerResult(analyzer_name=" ", signal=0.0, confidence=0.0)


def test_execution_metadata_defaults():
    meta = FundamentalExecutionMetadata(total_duration_ms=10.0)
    assert meta.analyzer_durations_ms == {}
    assert meta.features_from_cache == []
    assert meta.features_computed_fresh == []


def test_analysis_result_defaults():
    result = FundamentalAnalysisResult(
        symbol="AAPL", prediction=Prediction.BUY, confidence=0.7,
        expected_return=5.0, expected_volatility=10.0,
        execution_metadata=FundamentalExecutionMetadata(total_duration_ms=1.0),
    )
    assert result.evidence == []
    assert result.feature_importance == {}
    assert result.timestamp.tzinfo is not None


def test_analysis_result_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        FundamentalAnalysisResult(
            symbol="AAPL", prediction=Prediction.HOLD, confidence=1.5,
            expected_return=0.0, expected_volatility=0.0,
            execution_metadata=FundamentalExecutionMetadata(total_duration_ms=1.0),
        )
