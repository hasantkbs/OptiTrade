"""Tests for learning/weighting.py. Uses the real Feature Store and
real PostgreSQL (matching the established testing philosophy - real
infrastructure over mocks)."""
from datetime import datetime, timezone

import pytest

from decision_engine.config import DecisionEngineConfig
from decision_engine.models import Prediction
from feature_store.service import FeatureStoreService
from learning.config import LearningConfig
from learning.models import EngineOutcomeRecord, SampleSource, WeightingPolicy
from learning.persistence import LearningRepository
from learning.weighting import WeightCalculator

_ENGINE_NAME = "WeightTestEngine"


def _outcome(correct: bool) -> EngineOutcomeRecord:
    return EngineOutcomeRecord(
        sample_id=1, engine_name=_ENGINE_NAME, engine_version="v1", symbol="AAPL", source=SampleSource.LIVE,
        prediction=Prediction.BUY, confidence=0.7, expected_return=2.0, expected_volatility=15.0,
        decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5, evaluated=True,
        evaluated_at=datetime.now(timezone.utc), actual_return=2.0 if correct else -2.0,
        actual_volatility=12.0, correct=correct,
    )


@pytest.fixture
def calculator():
    repo = LearningRepository()
    feature_store = FeatureStoreService()
    config = LearningConfig(min_samples_for_weighting=3, max_weight_step=0.15)
    calc = WeightCalculator(feature_store=feature_store, repository=repo, config=config)
    yield calc
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_weight_updates WHERE engine_name = %s", (_ENGINE_NAME,))
    finally:
        repo._pool.putconn(conn)
    feature_store.online_store._client.delete(f"feature_store:{_ENGINE_NAME}:engine_accuracy_score")
    conn2 = feature_store.offline_store._pool.getconn()
    try:
        with conn2, conn2.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_ENGINE_NAME,))
    finally:
        feature_store.offline_store._pool.putconn(conn2)


def test_insufficient_samples_leaves_weight_unchanged(calculator):
    update = calculator.recompute_weight(_ENGINE_NAME, "v1", [_outcome(True)], policy=WeightingPolicy.EXPONENTIAL_DECAY)
    assert update.old_weight == update.new_weight
    assert "insufficient" in update.reason


def test_high_accuracy_increases_weight(calculator):
    outcomes = [_outcome(True)] * 5
    update = calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.EXPONENTIAL_DECAY)
    assert update.new_weight > update.old_weight


def test_low_accuracy_decreases_weight(calculator):
    outcomes = [_outcome(False)] * 5
    update = calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.EXPONENTIAL_DECAY)
    assert update.new_weight < update.old_weight


def test_weight_change_never_exceeds_configured_step(calculator):
    outcomes = [_outcome(True)] * 20  # 100% accuracy -> raw target would be far above 1.0
    update = calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.EXPONENTIAL_DECAY)
    assert abs(update.new_weight - update.old_weight) <= calculator.config.max_weight_step + 1e-9


def test_weight_is_persisted_to_feature_store(calculator):
    outcomes = [_outcome(True)] * 5
    update = calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.EXPONENTIAL_DECAY)
    record = calculator.feature_store.get_latest_feature(_ENGINE_NAME, calculator.config.accuracy_feature_name)
    assert record is not None
    assert record.value == update.new_weight


def test_weight_is_persisted_to_repository_history(calculator):
    outcomes = [_outcome(True)] * 5
    calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.EXPONENTIAL_DECAY)
    history = calculator.repository.get_weight_update_history(_ENGINE_NAME, "v1")
    assert len(history) == 1


def test_rolling_average_policy_produces_a_weight(calculator):
    outcomes = [_outcome(True)] * 5
    update = calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.ROLLING_AVERAGE)
    assert update.policy == WeightingPolicy.ROLLING_AVERAGE
    assert update.new_weight != update.old_weight


def test_bayesian_policy_produces_a_weight(calculator):
    outcomes = [_outcome(True)] * 5
    update = calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.BAYESIAN)
    assert update.policy == WeightingPolicy.BAYESIAN
    assert update.new_weight != update.old_weight


def test_defaults_to_decision_engine_default_weight_when_none_persisted(calculator):
    outcomes = [_outcome(True)] * 3
    update = calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.EXPONENTIAL_DECAY)
    assert update.old_weight == DecisionEngineConfig().default_accuracy_weight


def test_unknown_policy_raises_value_error(calculator):
    outcomes = [_outcome(True)] * 5
    with pytest.raises(ValueError):
        calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy="not_a_real_policy")


def test_weight_never_exceeds_configured_bounds_over_many_cycles(calculator):
    outcomes = [_outcome(True)] * 20
    for _ in range(50):
        update = calculator.recompute_weight(_ENGINE_NAME, "v1", outcomes, policy=WeightingPolicy.EXPONENTIAL_DECAY)
    assert calculator.config.min_weight <= update.new_weight <= calculator.config.max_weight
