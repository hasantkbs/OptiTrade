"""Tests for backend/pipeline/executor.py."""
import time

import pytest

from decision_engine.models import EngineVote, Prediction
from pipeline.config import PipelineConfig
from pipeline.executor import ParallelEngineExecutor
from pipeline.models import EngineExecutionStatus


class _FastEngine:
    engine_name = "Fast"
    engine_version = "v1"

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version, prediction=Prediction.BUY,
            confidence=0.8, expected_return=2.0, volatility=10.0, evidence=["e"],
        )


class _SlowEngine:
    engine_name = "Slow"
    engine_version = "v1"

    def __init__(self, delay: float):
        self._delay = delay

    def vote(self, symbol: str) -> EngineVote:
        time.sleep(self._delay)
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version, prediction=Prediction.SELL,
            confidence=0.5, expected_return=-1.0, volatility=5.0, evidence=["e"],
        )


class _FailingEngine:
    engine_name = "Failing"
    engine_version = "v1"

    def vote(self, symbol: str):
        raise RuntimeError("simulated engine failure")


class _InvalidVoteEngine:
    engine_name = "InvalidVote"
    engine_version = "v1"

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version, prediction=Prediction.HOLD,
            confidence=0.5, expected_return=float("nan"), volatility=1.0, evidence=[],
        )


class _FlakyEngine:
    engine_name = "Flaky"
    engine_version = "v1"

    def __init__(self, fail_times: int):
        self._fail_times = fail_times
        self.calls = 0

    def vote(self, symbol: str) -> EngineVote:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("transient failure")
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version, prediction=Prediction.BUY,
            confidence=0.6, expected_return=1.0, volatility=8.0, evidence=["recovered"],
        )


def test_successful_engine_returns_success_status():
    executor = ParallelEngineExecutor(config=PipelineConfig(engine_timeout_seconds=2.0, max_retries=0))
    results = executor.collect_votes([_FastEngine()], "AAPL")
    assert results[0].status == EngineExecutionStatus.SUCCESS
    assert results[0].vote.prediction == Prediction.BUY
    assert results[0].attempts == 1


def test_timeout_is_enforced_and_does_not_block_the_caller():
    config = PipelineConfig(engine_timeout_seconds=0.3, max_retries=0)
    executor = ParallelEngineExecutor(config=config)

    started = time.perf_counter()
    results = executor.collect_votes([_SlowEngine(delay=2.0)], "AAPL")
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, "caller must not block for the engine's full duration"
    assert results[0].status == EngineExecutionStatus.TIMEOUT
    assert results[0].error_type == "TimeoutError"
    assert results[0].vote is None


def test_failing_engine_returns_failed_status():
    executor = ParallelEngineExecutor(config=PipelineConfig(max_retries=0))
    results = executor.collect_votes([_FailingEngine()], "AAPL")
    assert results[0].status == EngineExecutionStatus.FAILED
    assert results[0].error_type == "RuntimeError"


def test_invalid_vote_returns_invalid_status():
    executor = ParallelEngineExecutor(config=PipelineConfig(max_retries=0))
    results = executor.collect_votes([_InvalidVoteEngine()], "AAPL")
    assert results[0].status == EngineExecutionStatus.INVALID
    assert results[0].error_type == "InvalidVoteError"


def test_retry_recovers_from_a_transient_failure():
    flaky = _FlakyEngine(fail_times=1)
    executor = ParallelEngineExecutor(config=PipelineConfig(max_retries=2))
    results = executor.collect_votes([flaky], "AAPL")
    assert results[0].status == EngineExecutionStatus.SUCCESS
    assert results[0].attempts == 2
    assert flaky.calls == 2


def test_retry_gives_up_after_max_retries():
    flaky = _FlakyEngine(fail_times=10)
    executor = ParallelEngineExecutor(config=PipelineConfig(max_retries=2))
    results = executor.collect_votes([flaky], "AAPL")
    assert results[0].status == EngineExecutionStatus.FAILED
    assert results[0].attempts == 3
    assert flaky.calls == 3


def test_multiple_engines_run_concurrently_not_serially():
    engines = [_SlowEngine(delay=0.5) for _ in range(4)]
    for i, engine in enumerate(engines):
        engine.engine_name = f"Slow{i}"
    executor = ParallelEngineExecutor(config=PipelineConfig(engine_timeout_seconds=2.0, max_retries=0, max_parallel_workers=8))

    started = time.perf_counter()
    results = executor.collect_votes(engines, "AAPL")
    elapsed = time.perf_counter() - started

    assert elapsed < 1.5, "four 0.5s engines run in parallel should take much less than 2s total"
    assert all(r.status == EngineExecutionStatus.SUCCESS for r in results)


def test_one_engine_failing_does_not_affect_others():
    executor = ParallelEngineExecutor(config=PipelineConfig(max_retries=0))
    results = executor.collect_votes([_FastEngine(), _FailingEngine()], "AAPL")
    statuses = {r.engine_name: r.status for r in results}
    assert statuses["Fast"] == EngineExecutionStatus.SUCCESS
    assert statuses["Failing"] == EngineExecutionStatus.FAILED


def test_executor_defaults_to_real_config():
    executor = ParallelEngineExecutor()
    assert isinstance(executor.config, PipelineConfig)
