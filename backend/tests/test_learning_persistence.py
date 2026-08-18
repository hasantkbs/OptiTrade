"""Tests for learning/persistence.py against the real PostgreSQL
database (matching the established testing philosophy of this
project - real infrastructure over mocks for persistence layers)."""
from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.models import EngineVote, Prediction
from learning.models import (
    AccuracyMetrics,
    DriftSignal,
    DriftType,
    LearningSample,
    RollingWindow,
    SampleSource,
    WeightingPolicy,
    WeightUpdate,
)
from learning.persistence import LearningRepository

_ENGINE = "PersistTestEngine"
_SYMBOL = "PERSISTX"


@pytest.fixture
def repository():
    repo = LearningRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
            cur.execute("DELETE FROM learning_accuracy_metrics WHERE engine_name = %s", (_ENGINE,))
            cur.execute("DELETE FROM learning_weight_updates WHERE engine_name = %s", (_ENGINE,))
            cur.execute("DELETE FROM learning_drift_signals WHERE engine_name = %s", (_ENGINE,))
    finally:
        repo._pool.putconn(conn)


def _sample(decided_at=None, horizon=5) -> LearningSample:
    vote = EngineVote(
        engine_name=_ENGINE, engine_version="v1", prediction=Prediction.BUY,
        confidence=0.7, expected_return=2.0, volatility=15.0, evidence=["e"],
        timestamp=decided_at or datetime.now(timezone.utc),
    )
    return LearningSample(
        symbol=_SYMBOL, source=SampleSource.LIVE, decision=Prediction.BUY, confidence=0.7,
        expected_return=2.0, expected_volatility=15.0, engine_results=[vote], evidence=["e"],
        decided_at=decided_at or datetime.now(timezone.utc), evaluation_horizon_days=horizon,
    )


def test_save_sample_returns_an_id(repository):
    sample_id = repository.save_sample(_sample())
    assert isinstance(sample_id, int)


def test_get_pending_samples_excludes_samples_within_horizon(repository):
    repository.save_sample(_sample(decided_at=datetime.now(timezone.utc), horizon=5))
    pending = repository.get_pending_samples(datetime.now(timezone.utc))
    assert all(p.symbol != _SYMBOL for p in pending)


def test_get_pending_samples_includes_matured_samples(repository):
    old = datetime.now(timezone.utc) - timedelta(days=10)
    repository.save_sample(_sample(decided_at=old, horizon=5))
    pending = repository.get_pending_samples(datetime.now(timezone.utc))
    assert any(p.symbol == _SYMBOL for p in pending)


def test_mark_sample_evaluated_updates_fields(repository):
    sample_id = repository.save_sample(_sample())
    now = datetime.now(timezone.utc)
    repository.mark_sample_evaluated(sample_id, actual_return=3.0, actual_volatility=10.0, correct=True, evaluated_at=now)
    pending = repository.get_pending_samples(now + timedelta(days=30))
    assert all(p.id != sample_id for p in pending)


def test_mark_engine_outcomes_evaluated_updates_per_engine_row(repository):
    sample_id = repository.save_sample(_sample())
    now = datetime.now(timezone.utc)
    repository.mark_engine_outcomes_evaluated(
        sample_id, actual_return=3.0, actual_volatility=10.0,
        per_engine_correct=[(_ENGINE, "v1", True)], evaluated_at=now,
    )
    outcomes = repository.get_engine_outcomes(_ENGINE, "v1", since=now - timedelta(days=1))
    assert outcomes[0].correct is True
    assert outcomes[0].actual_return == 3.0


def test_get_engine_outcomes_only_evaluated_filter(repository):
    repository.save_sample(_sample())
    since = datetime.now(timezone.utc) - timedelta(days=1)
    evaluated_only = repository.get_engine_outcomes(_ENGINE, "v1", since=since, only_evaluated=True)
    all_outcomes = repository.get_engine_outcomes(_ENGINE, "v1", since=since, only_evaluated=False)
    assert len(evaluated_only) == 0
    assert len(all_outcomes) == 1


def test_distinct_engines_includes_saved_engine(repository):
    repository.save_sample(_sample())
    assert (_ENGINE, "v1") in repository.distinct_engines()


def test_save_and_get_latest_accuracy(repository):
    metrics = AccuracyMetrics(
        engine_name=_ENGINE, engine_version="v1", window=RollingWindow.SEVEN_DAY, sample_count=10,
        accuracy=0.7, precision=0.6, recall=0.65, calibration_error=0.1, confidence_reliability=0.9,
        expected_return_error=1.0, volatility_error=2.0,
    )
    repository.save_accuracy_metrics(metrics)
    latest = repository.get_latest_accuracy(_ENGINE, "v1", RollingWindow.SEVEN_DAY)
    assert latest.accuracy == 0.7


def test_get_latest_accuracy_returns_none_when_absent(repository):
    assert repository.get_latest_accuracy("NoSuchEngine", "v1", RollingWindow.SEVEN_DAY) is None


def test_get_latest_accuracy_for_windows_matches_individual_lookups(repository):
    for window, accuracy_value in ((RollingWindow.SEVEN_DAY, 0.5), (RollingWindow.THIRTY_DAY, 0.6), (RollingWindow.LIFETIME, 0.7)):
        repository.save_accuracy_metrics(AccuracyMetrics(
            engine_name=_ENGINE, engine_version="v1", window=window, sample_count=10,
            accuracy=accuracy_value, precision=0.6, recall=0.6, calibration_error=0.1,
            confidence_reliability=0.9, expected_return_error=1.0, volatility_error=2.0,
        ))

    by_window = repository.get_latest_accuracy_for_windows(
        _ENGINE, "v1", [RollingWindow.SEVEN_DAY, RollingWindow.THIRTY_DAY, RollingWindow.NINETY_DAY, RollingWindow.LIFETIME],
    )

    assert set(by_window.keys()) == {RollingWindow.SEVEN_DAY, RollingWindow.THIRTY_DAY, RollingWindow.LIFETIME}
    assert by_window[RollingWindow.SEVEN_DAY].accuracy == pytest.approx(0.5)
    assert by_window[RollingWindow.THIRTY_DAY].accuracy == pytest.approx(0.6)
    assert by_window[RollingWindow.LIFETIME].accuracy == pytest.approx(0.7)
    # NINETY_DAY was never saved - matches get_latest_accuracy's own "absent -> not present" semantics.
    for window in by_window:
        individual = repository.get_latest_accuracy(_ENGINE, "v1", window)
        assert individual.accuracy == pytest.approx(by_window[window].accuracy)


def test_get_latest_accuracy_for_windows_only_returns_the_most_recent_row_per_window(repository):
    for accuracy_value in (0.4, 0.5, 0.6):
        repository.save_accuracy_metrics(AccuracyMetrics(
            engine_name=_ENGINE, engine_version="v1", window=RollingWindow.LIFETIME, sample_count=10,
            accuracy=accuracy_value, precision=0.6, recall=0.6, calibration_error=0.1,
            confidence_reliability=0.9, expected_return_error=1.0, volatility_error=2.0,
        ))
    by_window = repository.get_latest_accuracy_for_windows(_ENGINE, "v1", [RollingWindow.LIFETIME])
    assert by_window[RollingWindow.LIFETIME].accuracy == pytest.approx(0.6)


def test_get_latest_accuracy_for_windows_returns_empty_dict_when_absent(repository):
    assert repository.get_latest_accuracy_for_windows("NoSuchEngine", "v1", list(RollingWindow)) == {}


def test_get_latest_accuracy_for_windows_returns_empty_dict_for_empty_window_list(repository):
    assert repository.get_latest_accuracy_for_windows(_ENGINE, "v1", []) == {}


def test_get_latest_accuracy_for_windows_issues_a_single_query_not_one_per_window(repository, monkeypatch):
    """The whole point of this method: replace an O(windows) query
    count with O(1) - a dashboard building one engine's accuracy
    snapshot across every RollingWindow must not open one connection
    per window."""
    connection_count = 0
    real_connection = repository._connection

    def _counting_connection():
        nonlocal connection_count
        connection_count += 1
        return real_connection()

    monkeypatch.setattr(repository, "_connection", _counting_connection)
    repository.get_latest_accuracy_for_windows(_ENGINE, "v1", list(RollingWindow))
    assert connection_count == 1


def test_accuracy_history_orders_most_recent_first(repository):
    for accuracy_value in (0.5, 0.6, 0.7):
        metrics = AccuracyMetrics(
            engine_name=_ENGINE, engine_version="v1", window=RollingWindow.LIFETIME, sample_count=10,
            accuracy=accuracy_value, precision=0.6, recall=0.6, calibration_error=0.1,
            confidence_reliability=0.9, expected_return_error=1.0, volatility_error=2.0,
        )
        repository.save_accuracy_metrics(metrics)
    history = repository.get_accuracy_history(_ENGINE, "v1", RollingWindow.LIFETIME, limit=10)
    assert history[0].accuracy == 0.7


def test_save_and_get_latest_weight_update(repository):
    update = WeightUpdate(
        engine_name=_ENGINE, engine_version="v1", old_weight=1.0, new_weight=1.1,
        policy=WeightingPolicy.EXPONENTIAL_DECAY, reason="test",
    )
    repository.save_weight_update(update)
    latest = repository.get_latest_weight_update(_ENGINE, "v1")
    assert latest.new_weight == 1.1


def test_weight_update_history_orders_most_recent_first(repository):
    for weight in (1.0, 1.1, 1.2):
        repository.save_weight_update(
            WeightUpdate(
                engine_name=_ENGINE, engine_version="v1", old_weight=weight - 0.1, new_weight=weight,
                policy=WeightingPolicy.EXPONENTIAL_DECAY, reason="test",
            )
        )
    history = repository.get_weight_update_history(_ENGINE, "v1", limit=10)
    assert history[0].new_weight == 1.2


def test_save_and_get_recent_drift_signals(repository):
    signal = DriftSignal(
        engine_name=_ENGINE, engine_version="v1", drift_type=DriftType.IMPROVING, magnitude=0.1,
        recent_window=RollingWindow.SEVEN_DAY, baseline_window=RollingWindow.THIRTY_DAY, evidence="test",
    )
    repository.save_drift_signal(signal)
    signals = repository.get_recent_drift_signals(_ENGINE, "v1")
    assert signals[0].drift_type == DriftType.IMPROVING


def test_ping_returns_true(repository):
    assert repository.ping() is True


# ─────────────────────────────────────────────────────────────────────────
# Real database-error wrapping (closed pool fault injection, matching the
# pattern used in test_feature_store_offline_store.py)
# ─────────────────────────────────────────────────────────────────────────

def test_save_sample_wraps_a_real_database_error():
    from learning.exceptions import LearningPersistenceError

    isolated_repo = LearningRepository()
    isolated_repo._pool.closeall()
    with pytest.raises(LearningPersistenceError):
        isolated_repo.save_sample(_sample())


def test_get_pending_samples_wraps_a_real_database_error():
    from learning.exceptions import LearningPersistenceError

    isolated_repo = LearningRepository()
    isolated_repo._pool.closeall()
    with pytest.raises(LearningPersistenceError):
        isolated_repo.get_pending_samples(datetime.now(timezone.utc))
