"""Tests for pipeline/models.py, config.py, context.py, errors.py."""
import pytest
from pydantic import ValidationError

from pipeline.config import PipelineConfig
from pipeline.context import PipelineContext
from pipeline.errors import PipelineError, PipelineExecutionError
from pipeline.models import (
    EngineBreakdownItem,
    EngineExecutionResult,
    EngineExecutionStatus,
    PipelineMetadata,
    PipelineResponse,
    QuantAnalysisRequest,
    RiskAssessment,
)
from decision_engine.models import Prediction


def test_quant_analysis_request_defaults_asset_type():
    request = QuantAnalysisRequest(symbol="AAPL")
    assert request.asset_type == "stock"


def test_engine_execution_result_requires_nonneg_duration():
    with pytest.raises(ValidationError):
        EngineExecutionResult(
            engine_name="E", engine_version="v1", status=EngineExecutionStatus.SUCCESS,
            duration_ms=-1.0, attempts=1,
        )


def test_engine_breakdown_item_allows_none_vote_fields():
    item = EngineBreakdownItem(engine_name="E", engine_version="v1", status=EngineExecutionStatus.FAILED)
    assert item.prediction is None
    assert item.evidence == []


def test_risk_assessment_bounds_data_sufficiency():
    with pytest.raises(ValidationError):
        RiskAssessment(risk_level="LOW", expected_volatility=5.0, data_sufficiency=1.5)


def test_pipeline_metadata_defaults_stage_durations_empty():
    metadata = PipelineMetadata(
        pipeline_version="v1", total_duration_ms=10.0, engines_available=3, engines_succeeded=3, degraded=False,
    )
    assert metadata.stage_durations_ms == {}


def test_pipeline_response_construction():
    response = PipelineResponse(
        symbol="AAPL", decision=Prediction.HOLD, confidence=0.5, expected_return=1.0, expected_volatility=10.0,
        risk=RiskAssessment(risk_level="LOW", expected_volatility=10.0, data_sufficiency=1.0),
        explanation="test",
        metadata=PipelineMetadata(
            pipeline_version="v1", total_duration_ms=1.0, engines_available=3, engines_succeeded=3, degraded=False,
        ),
    )
    assert response.engine_breakdown == []
    assert response.evidence == []


def test_pipeline_config_defaults():
    config = PipelineConfig()
    assert config.engine_timeout_seconds == 8.0
    assert config.max_retries == 1


def test_pipeline_config_from_env(monkeypatch):
    monkeypatch.setenv("PIPELINE_ENGINE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("PIPELINE_MAX_RETRIES", "5")
    config = PipelineConfig.from_env()
    assert config.engine_timeout_seconds == 3.5
    assert config.max_retries == 5


def test_pipeline_context_records_stage_durations():
    context = PipelineContext(symbol="AAPL")
    context.record_stage("load_features", 5.0)
    context.record_stage("engines", 100.0)
    assert context.stage_durations_ms == {"load_features": 5.0, "engines": 100.0}
    assert context.execution_results == []
    assert context.decision_output is None


def test_pipeline_errors_are_exceptions():
    assert issubclass(PipelineExecutionError, PipelineError)
    assert issubclass(PipelineError, Exception)
