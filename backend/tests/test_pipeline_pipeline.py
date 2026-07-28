"""Tests for backend/pipeline/pipeline.py. Uses fakes for every
dependency so orchestration logic (stage sequencing, aggregation,
graceful degradation, response building) is tested in full isolation
from real infrastructure - the real, infrastructure-backed end-to-end
path is covered separately in test_pipeline_service.py."""
from datetime import datetime, timezone

import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from explanation_engine.models import Explanation, ExplanationProvider
from pipeline.config import PipelineConfig
from pipeline.models import EngineExecutionResult, EngineExecutionStatus
from pipeline.pipeline import Pipeline


class _FakeEngine:
    def __init__(self, name: str, prediction: Prediction, confidence: float = 0.7):
        self.engine_name = name
        self.engine_version = "v1"
        self._prediction = prediction
        self._confidence = confidence

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version, prediction=self._prediction,
            confidence=self._confidence, expected_return=2.0, volatility=12.0, evidence=[f"{self.engine_name} evidence"],
        )


class _FailingEngine:
    engine_name = "Failing"
    engine_version = "v1"

    def vote(self, symbol: str):
        raise RuntimeError("boom")


class _FakeFeatureStore:
    def __init__(self, raises: bool = False):
        self._raises = raises
        self.health_check_calls = 0

    def health_check(self):
        self.health_check_calls += 1
        if self._raises:
            raise RuntimeError("feature store unreachable")
        return {"online_store_available": True, "offline_store_available": True}


class _FakeWeightProvider:
    def __init__(self, weights=None):
        self._weights = weights or {}

    def get_weight(self, engine_name: str) -> float:
        return self._weights.get(engine_name, 1.0)


class _FakeExecutionRepository:
    def __init__(self, raises: bool = False):
        self._raises = raises
        self.saved = []

    def save(self, output: DecisionOutput) -> None:
        if self._raises:
            raise RuntimeError("persistence unavailable")
        self.saved.append(output)

    def get_recent(self, symbol, limit=10):
        return []


class _FakeExplanationEngine:
    def __init__(self, text: str = "fake explanation"):
        self._text = text
        self.calls = []

    def explain(self, decision: DecisionOutput, symbol: str) -> Explanation:
        self.calls.append((decision, symbol))
        return Explanation(text=self._text, provider=ExplanationProvider.FALLBACK)


class _FakeLearningService:
    def __init__(self, raises: bool = False):
        self._raises = raises
        self.recorded = []

    def record_decision(self, output: DecisionOutput):
        if self._raises:
            raise RuntimeError("learning unavailable")
        self.recorded.append(output)


def _build_pipeline(engines, **overrides):
    defaults = dict(
        engines=engines,
        feature_store=_FakeFeatureStore(),
        weight_provider=_FakeWeightProvider(),
        execution_repository=_FakeExecutionRepository(),
        explanation_engine=_FakeExplanationEngine(),
        learning_service=_FakeLearningService(),
        config=PipelineConfig(engine_timeout_seconds=2.0, max_retries=0),
    )
    defaults.update(overrides)
    return Pipeline(**defaults)


def test_all_engines_succeed_produces_buy_decision():
    engines = [
        _FakeEngine("TechnicalEngine", Prediction.BUY),
        _FakeEngine("FundamentalEngine", Prediction.BUY),
        _FakeEngine("NewsEngine", Prediction.BUY),
    ]
    pipeline = _build_pipeline(engines)
    response = pipeline.run("AAPL")

    assert response.decision == Prediction.BUY
    assert response.metadata.engines_succeeded == 3
    assert response.metadata.degraded is False
    assert len(response.engine_breakdown) == 3


def test_partial_engine_failure_produces_degraded_response():
    engines = [
        _FakeEngine("TechnicalEngine", Prediction.BUY),
        _FailingEngine(),
    ]
    pipeline = _build_pipeline(engines)
    response = pipeline.run("AAPL")

    assert response.metadata.engines_available == 2
    assert response.metadata.engines_succeeded == 1
    assert response.metadata.degraded is True
    statuses = {item.engine_name: item.status for item in response.engine_breakdown}
    assert statuses["Failing"] == EngineExecutionStatus.FAILED
    assert statuses["Failing"] is not None


def test_all_engines_failing_produces_neutral_hold():
    pipeline = _build_pipeline([_FailingEngine()])
    response = pipeline.run("AAPL")

    assert response.decision == Prediction.HOLD
    assert response.confidence == 0.0
    assert response.risk.data_sufficiency == 0.0
    assert response.metadata.degraded is True


def test_decision_is_persisted_via_execution_repository():
    repository = _FakeExecutionRepository()
    pipeline = _build_pipeline([_FakeEngine("TechnicalEngine", Prediction.BUY)], execution_repository=repository)
    pipeline.run("AAPL")
    assert len(repository.saved) == 1
    assert repository.saved[0].symbol == "AAPL"


def test_persistence_failure_does_not_break_the_response():
    repository = _FakeExecutionRepository(raises=True)
    pipeline = _build_pipeline([_FakeEngine("TechnicalEngine", Prediction.BUY)], execution_repository=repository)
    response = pipeline.run("AAPL")
    assert response.decision == Prediction.BUY  # request still succeeds


def test_explanation_engine_is_called_with_the_decision_output():
    explanation_engine = _FakeExplanationEngine(text="a specific explanation")
    pipeline = _build_pipeline([_FakeEngine("TechnicalEngine", Prediction.BUY)], explanation_engine=explanation_engine)
    response = pipeline.run("AAPL")

    assert response.explanation == "a specific explanation"
    assert len(explanation_engine.calls) == 1
    assert explanation_engine.calls[0][1] == "AAPL"


def test_learning_service_records_every_successful_decision():
    learning_service = _FakeLearningService()
    pipeline = _build_pipeline([_FakeEngine("TechnicalEngine", Prediction.BUY)], learning_service=learning_service)
    pipeline.run("AAPL")
    assert len(learning_service.recorded) == 1
    assert learning_service.recorded[0].symbol == "AAPL"


def test_learning_failure_does_not_break_the_response():
    learning_service = _FakeLearningService(raises=True)
    pipeline = _build_pipeline([_FakeEngine("TechnicalEngine", Prediction.BUY)], learning_service=learning_service)
    response = pipeline.run("AAPL")
    assert response.decision == Prediction.BUY


def test_feature_store_health_check_failure_does_not_break_the_response():
    pipeline = _build_pipeline([_FakeEngine("TechnicalEngine", Prediction.BUY)], feature_store=_FakeFeatureStore(raises=True))
    response = pipeline.run("AAPL")
    assert response.decision == Prediction.BUY


def test_risk_level_thresholds():
    config = PipelineConfig(low_volatility_threshold_pct=10.0, high_volatility_threshold_pct=25.0)

    low = _build_pipeline([_FakeEngine("E", Prediction.BUY)], config=config)
    low.engines[0].vote = lambda symbol: EngineVote(
        engine_name="E", engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
        expected_return=1.0, volatility=5.0, evidence=[],
    )
    assert low.run("AAPL").risk.risk_level == "LOW"

    medium = _build_pipeline([_FakeEngine("E", Prediction.BUY)], config=config)
    medium.engines[0].vote = lambda symbol: EngineVote(
        engine_name="E", engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
        expected_return=1.0, volatility=15.0, evidence=[],
    )
    assert medium.run("AAPL").risk.risk_level == "MEDIUM"

    high = _build_pipeline([_FakeEngine("E", Prediction.BUY)], config=config)
    high.engines[0].vote = lambda symbol: EngineVote(
        engine_name="E", engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
        expected_return=1.0, volatility=30.0, evidence=[],
    )
    assert high.run("AAPL").risk.risk_level == "HIGH"


def test_evidence_is_attributed_per_engine():
    engines = [_FakeEngine("TechnicalEngine", Prediction.BUY), _FakeEngine("FundamentalEngine", Prediction.BUY)]
    pipeline = _build_pipeline(engines)
    response = pipeline.run("AAPL")
    assert any("TechnicalEngine:" in e for e in response.evidence)
    assert any("FundamentalEngine:" in e for e in response.evidence)


def test_stage_durations_are_recorded_for_every_stage():
    pipeline = _build_pipeline([_FakeEngine("TechnicalEngine", Prediction.BUY)])
    response = pipeline.run("AAPL")
    expected_stages = {"load_features", "engines", "decision", "explanation", "learning"}
    assert expected_stages <= set(response.metadata.stage_durations_ms.keys())


def test_persist_decision_is_a_noop_when_decision_output_is_none():
    repository = _FakeExecutionRepository()
    pipeline = _build_pipeline([_FakeEngine("TechnicalEngine", Prediction.BUY)], execution_repository=repository)
    pipeline._persist_decision(None)
    assert repository.saved == []


def test_engine_breakdown_includes_failed_engines_with_no_vote_data():
    pipeline = _build_pipeline([_FailingEngine()])
    response = pipeline.run("AAPL")
    item = response.engine_breakdown[0]
    assert item.status == EngineExecutionStatus.FAILED
    assert item.prediction is None
    assert item.confidence is None
