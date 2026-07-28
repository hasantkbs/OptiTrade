"""Tests for learning/evaluator.py. Uses the real PostgreSQL-backed
LearningRepository with a fake, deterministic price fetcher (network
calls to a real provider are exercised separately in
test_learning_service.py's real end-to-end test)."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from learning.config import LearningConfig
from learning.evaluator import OutcomeEvaluator
from learning.persistence import LearningRepository
from learning.tracker import SampleTracker

_SYMBOL = "EVALX"


def _rising_price_fetcher(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    prices = [100 + i * 1.0 for i in range(len(dates))]
    return pd.DataFrame({"Close": prices}, index=dates)


def _falling_price_fetcher(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    prices = [100 - i * 1.0 for i in range(len(dates))]
    return pd.DataFrame({"Close": prices}, index=dates)


def _flat_price_fetcher(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)


def _no_data_fetcher(symbol, start, end):
    return None


@pytest.fixture
def repository():
    repo = LearningRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
    finally:
        repo._pool.putconn(conn)


def _tracked_sample(repository, prediction: Prediction, horizon_days: int = 5, days_ago: int = 10):
    config = LearningConfig(evaluation_horizon_days=horizon_days)
    tracker = SampleTracker(repository=repository, config=config)
    decided_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    vote = EngineVote(
        engine_name="EvalTestEngine", engine_version="v1", prediction=prediction,
        confidence=0.7, expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at,
    )
    output = DecisionOutput(
        symbol=_SYMBOL, decision=prediction, confidence=0.7, expected_return=2.0,
        expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
        evidence=["e"], engine_results=[vote], timestamp=decided_at,
    )
    return tracker.track_decision(output)


def test_evaluate_pending_marks_a_matured_sample_evaluated(repository):
    sample = _tracked_sample(repository, Prediction.BUY)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=_rising_price_fetcher)
    count = evaluator.evaluate_pending(now=datetime.now(timezone.utc))
    assert count == 1

    pending = repository.get_pending_samples(datetime.now(timezone.utc))
    assert all(p.id != sample.id for p in pending)


def test_evaluate_pending_skips_samples_within_the_horizon(repository):
    _tracked_sample(repository, Prediction.BUY, days_ago=1)  # horizon 5 days, only 1 elapsed
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=_rising_price_fetcher)
    count = evaluator.evaluate_pending(now=datetime.now(timezone.utc))
    assert count == 0


def test_buy_prediction_correct_when_price_rises(repository):
    sample = _tracked_sample(repository, Prediction.BUY)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=_rising_price_fetcher)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    outcomes = repository.get_engine_outcomes("EvalTestEngine", "v1", since=datetime.now(timezone.utc) - timedelta(days=30))
    assert outcomes[0].correct is True
    assert outcomes[0].actual_return > 0


def test_buy_prediction_incorrect_when_price_falls(repository):
    _tracked_sample(repository, Prediction.BUY)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=_falling_price_fetcher)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    outcomes = repository.get_engine_outcomes("EvalTestEngine", "v1", since=datetime.now(timezone.utc) - timedelta(days=30))
    assert outcomes[0].correct is False
    assert outcomes[0].actual_return < 0


def test_hold_prediction_correct_when_price_is_flat(repository):
    _tracked_sample(repository, Prediction.HOLD)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(hold_band_pct=1.0), price_fetcher=_flat_price_fetcher)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    outcomes = repository.get_engine_outcomes("EvalTestEngine", "v1", since=datetime.now(timezone.utc) - timedelta(days=30))
    assert outcomes[0].correct is True
    assert outcomes[0].actual_return == pytest.approx(0.0)


def test_sell_prediction_correct_when_price_falls(repository):
    _tracked_sample(repository, Prediction.SELL)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=_falling_price_fetcher)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    outcomes = repository.get_engine_outcomes("EvalTestEngine", "v1", since=datetime.now(timezone.utc) - timedelta(days=30))
    assert outcomes[0].correct is True


def test_sample_left_unevaluated_when_no_price_data_available(repository):
    _tracked_sample(repository, Prediction.BUY)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=_no_data_fetcher)
    count = evaluator.evaluate_pending(now=datetime.now(timezone.utc))
    assert count == 0

    pending = repository.get_pending_samples(datetime.now(timezone.utc))
    assert len(pending) >= 1


def test_actual_volatility_is_realized_from_price_series(repository):
    _tracked_sample(repository, Prediction.BUY)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=_rising_price_fetcher)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    outcomes = repository.get_engine_outcomes("EvalTestEngine", "v1", since=datetime.now(timezone.utc) - timedelta(days=30))
    assert outcomes[0].actual_volatility >= 0.0


def test_realized_volatility_with_a_single_return_is_zero_not_nan():
    # A window containing exactly two price points produces exactly one
    # daily return - pandas' sample std (ddof=1) is undefined for a
    # single value and returns NaN; this must degrade to 0.0 instead,
    # matching the "insufficient data" convention used everywhere else
    # in this function, not propagate a NaN volatility.
    import math

    from learning.evaluator import OutcomeEvaluator as Evaluator

    start = datetime.now(timezone.utc)
    end = start + timedelta(days=1)
    two_point_window = pd.DataFrame(
        {"Close": [100.0, 101.0]}, index=pd.date_range(start=start, periods=2, freq="D", tz="UTC"),
    )
    volatility = Evaluator._realized_volatility(two_point_window, start, end)
    assert volatility == 0.0
    assert not math.isnan(volatility)


def test_evaluator_defaults_to_real_repository_and_config():
    evaluator = OutcomeEvaluator()
    assert isinstance(evaluator.repository, LearningRepository)
    assert isinstance(evaluator.config, LearningConfig)


def test_price_on_or_after_handles_timezone_naive_index(repository):
    def naive_fetcher(symbol, start, end):
        dates = pd.date_range(start=start.replace(tzinfo=None), end=end.replace(tzinfo=None), freq="D")
        return pd.DataFrame({"Close": [100 + i for i in range(len(dates))]}, index=dates)

    _tracked_sample(repository, Prediction.BUY)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=naive_fetcher)
    count = evaluator.evaluate_pending(now=datetime.now(timezone.utc))
    assert count == 1


def test_no_outcome_when_start_price_is_zero(repository):
    def zero_start_fetcher(symbol, start, end):
        # The evaluator fetches from (decided_at - 1 day), so index 1 is the
        # first row at/after `decided_at` itself - that's the row picked as
        # the start price.
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        prices = [100.0, 0.0] + [100 + i for i in range(len(dates) - 2)]
        return pd.DataFrame({"Close": prices}, index=dates)

    _tracked_sample(repository, Prediction.BUY)
    evaluator = OutcomeEvaluator(repository=repository, config=LearningConfig(), price_fetcher=zero_start_fetcher)
    count = evaluator.evaluate_pending(now=datetime.now(timezone.utc))
    assert count == 0


def test_realized_volatility_is_zero_with_a_single_row_window():
    from learning.evaluator import OutcomeEvaluator as Evaluator

    start = datetime.now(timezone.utc)
    end = start + timedelta(days=1)
    single_row = pd.DataFrame({"Close": [100.0]}, index=pd.date_range(start=start, periods=1, freq="D", tz="UTC"))
    assert Evaluator._realized_volatility(single_row, start, end) == 0.0
