"""Tests for research_lab/benchmarking/."""
from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from learning.config import LearningConfig
from learning.evaluator import OutcomeEvaluator
from learning.models import RollingWindow, WeightingPolicy
from learning.persistence import LearningRepository
from learning.tracker import SampleTracker
from research_lab.benchmarking import comparator, policy_simulation
from research_lab.benchmarking.repository import BenchmarkRepository
from research_lab.benchmarking.service import BenchmarkService
from research_lab.config import ResearchLabConfig
from research_lab.models import BenchmarkSubjectType

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────
# comparator.py (pure)
# ─────────────────────────────────────────────────────────────────────────

def test_compare_detects_significant_difference():
    result = comparator.compare(
        BenchmarkSubjectType.MODEL, "a", "b",
        [5.0, 6.0, 5.5, 4.5, 6.5], [-5.0, -6.0, -4.5, -5.5, -6.5],
        RollingWindow.LIFETIME,
    )
    assert result.significant is True
    assert result.p_value < 0.05


def test_compare_not_significant_for_similar_distributions():
    result = comparator.compare(
        BenchmarkSubjectType.MODEL, "a", "b", [1.0, 1.1, 0.9, 1.05], [1.02, 0.98, 1.03, 1.0],
        RollingWindow.LIFETIME,
    )
    assert result.significant is False


def test_compare_with_insufficient_samples_defaults_p_value_to_one():
    result = comparator.compare(BenchmarkSubjectType.MODEL, "a", "b", [1.0], [], RollingWindow.LIFETIME)
    assert result.p_value == 1.0
    assert result.significant is False


def test_compare_includes_metrics_for_both_subjects():
    result = comparator.compare(
        BenchmarkSubjectType.ENGINE_VERSION, "v1", "v2", [1.0, 2.0, 3.0], [1.0, 1.0, 1.0], RollingWindow.LIFETIME,
    )
    assert "sharpe_ratio" in result.metrics_a
    assert "sharpe_ratio" in result.metrics_b


# ─────────────────────────────────────────────────────────────────────────
# policy_simulation.py
# ─────────────────────────────────────────────────────────────────────────

def _outcome(correct: bool):
    from decision_engine.models import Prediction as P
    from learning.models import EngineOutcomeRecord, SampleSource
    return EngineOutcomeRecord(
        sample_id=1, engine_name="E", engine_version="v1", symbol="AAPL", source=SampleSource.LIVE,
        prediction=P.BUY, confidence=0.7, expected_return=2.0, expected_volatility=15.0,
        decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5, evaluated=True,
        evaluated_at=datetime.now(timezone.utc), actual_return=2.0 if correct else -2.0,
        actual_volatility=12.0, correct=correct,
    )


def test_simulate_policy_target_insufficient_samples_returns_old_weight():
    config = LearningConfig(min_samples_for_weighting=100)
    target, reason = policy_simulation.simulate_policy_target(
        WeightingPolicy.EXPONENTIAL_DECAY, [_outcome(True)], old_weight=1.0, learning_config=config,
    )
    assert target == 1.0
    assert "insufficient" in reason


def test_simulate_policy_target_exponential_decay():
    outcomes = [_outcome(True)] * 5
    target, reason = policy_simulation.simulate_policy_target(WeightingPolicy.EXPONENTIAL_DECAY, outcomes, old_weight=1.0)
    assert target > 1.0


def test_simulate_policy_target_bayesian():
    outcomes = [_outcome(True)] * 5
    target, reason = policy_simulation.simulate_policy_target(WeightingPolicy.BAYESIAN, outcomes, old_weight=1.0)
    assert target > 1.0


def test_simulate_policy_target_unknown_policy_raises():
    outcomes = [_outcome(True)] * 5
    with pytest.raises(ValueError):
        policy_simulation.simulate_policy_target("not_a_policy", outcomes, old_weight=1.0)


# ─────────────────────────────────────────────────────────────────────────
# service.py (real Postgres)
# ─────────────────────────────────────────────────────────────────────────

_ENGINE = "BenchSvcRealTest"
_SYMBOL = "BNSVCX"


@pytest.fixture
def learning_setup():
    repo = LearningRepository()
    config = LearningConfig(evaluation_horizon_days=5, min_samples_for_weighting=1)
    tracker = SampleTracker(repository=repo, config=config)

    def fetcher(symbol, start, end):
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        return pd.DataFrame({"Close": [100 + i * 0.3 for i in range(len(dates))]}, index=dates)

    evaluator = OutcomeEvaluator(repository=repo, config=config, price_fetcher=fetcher)
    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    for i in range(5):
        vote = EngineVote(
            engine_name=_ENGINE, engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
            expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at - timedelta(days=i),
        )
        output = DecisionOutput(
            symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.7, expected_return=2.0,
            expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
            evidence=["e"], engine_results=[vote], timestamp=decided_at - timedelta(days=i),
        )
        tracker.track_decision(output)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    yield repo, config

    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def benchmark_repository():
    repo = BenchmarkRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM research_benchmark_results WHERE subject_a IN ('v1', 'exponential_decay', 'set_a')")
    finally:
        repo._pool.putconn(conn)


def test_compare_engine_versions_sources_from_learning(learning_setup, benchmark_repository):
    repo, config = learning_setup
    svc = BenchmarkService(learning_repository=repo, repository=benchmark_repository, learning_config=config)
    result = svc.compare_engine_versions(_ENGINE, "v1", "v2", RollingWindow.LIFETIME)
    assert result.id is not None
    assert result.metrics_a["sample_count"] == 5.0
    assert result.metrics_b["sample_count"] == 0.0


def test_compare_weighting_policies_simulates_both_policies(learning_setup, benchmark_repository):
    repo, config = learning_setup
    svc = BenchmarkService(learning_repository=repo, repository=benchmark_repository, learning_config=config)
    result = svc.compare_weighting_policies(_ENGINE, "v1", WeightingPolicy.EXPONENTIAL_DECAY, WeightingPolicy.BAYESIAN)
    assert "target_weight" in result.metrics_a
    assert "target_weight" in result.metrics_b


def test_compare_feature_sets_is_a_generic_passthrough(benchmark_repository):
    svc = BenchmarkService(repository=benchmark_repository)
    result = svc.compare_feature_sets("set_a", [1.0, 2.0, 3.0], "set_b", [0.1, 0.2, 0.3], RollingWindow.LIFETIME)
    assert result.subject_type == BenchmarkSubjectType.FEATURE_SET


def test_service_defaults_to_real_dependencies():
    svc = BenchmarkService()
    assert isinstance(svc.learning_repository, LearningRepository)
    assert isinstance(svc.repository, BenchmarkRepository)


# ─────────────────────────────────────────────────────────────────────────
# repository.py read methods
# ─────────────────────────────────────────────────────────────────────────

def test_benchmark_repository_list_for_subjects(benchmark_repository):
    result = comparator.compare(
        BenchmarkSubjectType.FEATURE_SET, "set_a", "set_b", [1.0, 2.0], [0.1, 0.2], RollingWindow.LIFETIME,
    )
    benchmark_repository.save(result)
    results = benchmark_repository.list_for_subjects(BenchmarkSubjectType.FEATURE_SET, "set_a", "set_b")
    assert len(results) >= 1


def test_benchmark_repository_list_for_experiment(benchmark_repository):
    result = comparator.compare(
        BenchmarkSubjectType.FEATURE_SET, "set_a", "set_b", [1.0, 2.0], [0.1, 0.2], RollingWindow.LIFETIME,
        experiment_id=77,
    )
    benchmark_repository.save(result)
    results = benchmark_repository.list_for_experiment(77)
    assert any(r.subject_a == "set_a" for r in results)
