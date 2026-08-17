"""Tests for backend/pipeline/pipeline.py. Uses fakes for every
dependency so orchestration logic (stage sequencing, aggregation,
graceful degradation, response building) is tested in full isolation
from real infrastructure - the real, infrastructure-backed end-to-end
path is covered separately in test_pipeline_service.py."""
import threading
import time
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


# ─────────────────────────────────────────────────────────────────────────
# Weight-lookup failure resilience (production audit HIGH #2: "the weight
# lookup call in _decision_stage is the only pipeline stage without
# try/except - a Feature Store/weight lookup failure can turn an
# otherwise successful decision into HTTP 500").
# ─────────────────────────────────────────────────────────────────────────

class _RaisingWeightProvider:
    def get_weight(self, engine_name: str) -> float:
        raise RuntimeError("feature store unreachable")


def test_run_survives_a_weight_lookup_failure_instead_of_raising():
    engines = [
        _FakeEngine("TechnicalEngine", Prediction.BUY),
        _FakeEngine("FundamentalEngine", Prediction.BUY),
    ]
    pipeline = _build_pipeline(engines, weight_provider=_RaisingWeightProvider())
    response = pipeline.run("AAPL")  # must not raise

    assert response.decision == Prediction.BUY
    assert response.metadata.engines_succeeded == 2
    assert response.metadata.degraded is False  # both votes still succeeded - only their weight lookup failed
    assert len(response.engine_breakdown) == 2


def test_weight_lookup_failure_falls_back_to_the_configured_default_weight():
    engines = [_FakeEngine("TechnicalEngine", Prediction.BUY, confidence=0.9)]
    config = PipelineConfig(engine_timeout_seconds=2.0, max_retries=0)
    pipeline_with_failure = _build_pipeline(engines, weight_provider=_RaisingWeightProvider(), config=config)
    pipeline_with_default = _build_pipeline(
        engines, weight_provider=_FakeWeightProvider({"TechnicalEngine": 1.0}), config=config,
    )

    response_with_failure = pipeline_with_failure.run("AAPL")
    response_with_default = pipeline_with_default.run("AAPL")

    # A failed lookup must resolve to the same result as the provider's
    # own documented "no accuracy data" default (1.0, single-engine
    # case) - not an arbitrarily different weight.
    assert response_with_failure.confidence == response_with_default.confidence


# ─────────────────────────────────────────────────────────────────────────
# Concurrency regression (production audit's "self.pipeline.engines is
# shared and mutated per request while Pipeline.run() is simultaneously
# reading it" finding).
#
# `Pipeline`/`PipelineService` are process-wide singletons main.py runs
# concurrent requests through (a 16-thread executor pool) - engines were
# previously resolved per request and assigned to shared `self.engines`
# instance state, which `run()` then read from at several different
# points during a single call. Two overlapping `run()` calls with
# different engine compositions could interleave their write/reads and
# see each other's engine list. The fix threads each call's engines
# through as a local `PipelineContext.engines` value instead - this test
# proves that holds even under real concurrent execution with distinct
# per-call engine lists.
# ─────────────────────────────────────────────────────────────────────────

class _SlowFakeEngine:
    """Like _FakeEngine, but sleeps inside vote() - widens the window
    during which other concurrent `Pipeline.run()` calls on the SAME
    shared `pipeline` instance are also mid-flight, so a race on shared
    per-request state (were one still present) would actually be
    exercised rather than being merely theoretically possible."""

    def __init__(self, name: str, delay_seconds: float = 0.05):
        self.engine_name = name
        self.engine_version = "v1"
        self._delay_seconds = delay_seconds

    def vote(self, symbol: str) -> EngineVote:
        time.sleep(self._delay_seconds)
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version, prediction=Prediction.BUY,
            confidence=0.7, expected_return=2.0, volatility=12.0, evidence=[f"{self.engine_name} evidence"],
        )


def test_concurrent_runs_with_different_engine_lists_never_observe_each_others_engines():
    thread_count = 10
    # One shared Pipeline instance (as PipelineService holds one shared
    # singleton in production) - every thread below calls .run() on the
    # SAME object, each with its own, differently-sized/named engine list.
    pipeline = _build_pipeline([_SlowFakeEngine("placeholder")])

    results = {}
    errors = []

    def _run(thread_index: int) -> None:
        try:
            engines = [_SlowFakeEngine(f"Engine-{thread_index}-{j}") for j in range(thread_index + 1)]
            response = pipeline.run("AAPL", engines=engines)
            results[thread_index] = response
        except Exception as exc:  # pragma: no cover - failure path only
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert set(results.keys()) == set(range(thread_count))
    for i, response in results.items():
        expected_names = {f"Engine-{i}-{j}" for j in range(i + 1)}
        actual_names = {item.engine_name for item in response.engine_breakdown}
        assert actual_names == expected_names, (
            f"thread {i} observed engines {actual_names}, expected only its own {expected_names} - "
            f"a foreign or missing engine name means engine composition leaked across concurrent requests"
        )
        assert response.metadata.engines_available == i + 1
        assert response.metadata.engines_succeeded == i + 1
