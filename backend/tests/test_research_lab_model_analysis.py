"""Tests for research_lab/model_analysis/."""
from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.models import Prediction
from learning.models import EngineOutcomeRecord, RollingWindow, SampleSource
from research_lab.model_analysis import analyzer, metrics
from research_lab.model_analysis.repository import ModelAnalysisRepository
from research_lab.models import ModelAnalysisResult

# ─────────────────────────────────────────────────────────────────────────
# metrics.py (pure)
# ─────────────────────────────────────────────────────────────────────────

def test_expected_value_of_empty_returns_zero():
    assert metrics.expected_value([]) == 0.0


def test_expected_value_is_mean():
    assert metrics.expected_value([1.0, 2.0, 3.0]) == pytest.approx(2.0)


def test_sharpe_ratio_zero_with_fewer_than_two_returns():
    assert metrics.sharpe_ratio([1.0]) == 0.0


def test_sharpe_ratio_zero_when_no_variance():
    assert metrics.sharpe_ratio([2.0, 2.0, 2.0]) == 0.0


def test_sharpe_ratio_positive_for_consistently_positive_returns():
    assert metrics.sharpe_ratio([1.0, 2.0, 1.5, 3.0, 0.5]) > 0


def test_sortino_ratio_capped_when_no_downside():
    assert metrics.sortino_ratio([1.0, 2.0, 3.0]) == 10.0


def test_sortino_ratio_zero_when_no_downside_and_no_mean_excess():
    assert metrics.sortino_ratio([0.0, 0.0, 0.0]) == 0.0


def test_sortino_ratio_penalizes_downside_volatility():
    assert metrics.sortino_ratio([-5.0, 1.0, 2.0, -3.0, 4.0]) != 10.0


def test_max_drawdown_zero_for_monotonically_increasing_returns():
    assert metrics.max_drawdown([1.0, 1.0, 1.0, 1.0]) == pytest.approx(0.0)


def test_max_drawdown_nonzero_after_a_loss():
    drawdown = metrics.max_drawdown([5.0, -10.0, 2.0])
    assert drawdown > 0


def test_max_drawdown_of_empty_series():
    assert metrics.max_drawdown([]) == 0.0


# ─────────────────────────────────────────────────────────────────────────
# analyzer.py
# ─────────────────────────────────────────────────────────────────────────

def _outcome(correct: bool, actual_return: float) -> EngineOutcomeRecord:
    return EngineOutcomeRecord(
        sample_id=1, engine_name="E", engine_version="v1", symbol="AAPL", source=SampleSource.LIVE,
        prediction=Prediction.BUY, confidence=0.7, expected_return=2.0, expected_volatility=15.0,
        decided_at=datetime.now(timezone.utc), evaluation_horizon_days=5, evaluated=True,
        evaluated_at=datetime.now(timezone.utc), actual_return=actual_return, actual_volatility=12.0,
        correct=correct,
    )


def test_analyze_combines_accuracy_and_risk_metrics():
    outcomes = [_outcome(True, 2.0), _outcome(True, 3.0), _outcome(False, -1.0)]
    result = analyzer.analyze("E", "v1", RollingWindow.LIFETIME, outcomes)
    assert isinstance(result, ModelAnalysisResult)
    assert result.accuracy_metrics.sample_count == 3
    assert result.accuracy_metrics.accuracy == pytest.approx(2 / 3)
    assert result.expected_value == pytest.approx((2.0 + 3.0 - 1.0) / 3)


def test_analyze_with_no_outcomes_produces_zeroed_result():
    result = analyzer.analyze("E", "v1", RollingWindow.LIFETIME, [])
    assert result.accuracy_metrics.sample_count == 0
    assert result.sharpe_ratio == 0.0
    assert result.expected_value == 0.0


# ─────────────────────────────────────────────────────────────────────────
# repository.py (real Postgres)
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def repository():
    repo = ModelAnalysisRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM research_model_analysis WHERE engine_name = 'ModelAnalysisRepoTest'")
    finally:
        repo._pool.putconn(conn)


def test_save_and_get_history(repository):
    outcomes = [_outcome(True, 2.0), _outcome(True, 1.0)]
    result = analyzer.analyze("ModelAnalysisRepoTest", "v1", RollingWindow.LIFETIME, outcomes)
    repository.save(result)

    history = repository.get_history("ModelAnalysisRepoTest", "v1", RollingWindow.LIFETIME)
    assert len(history) == 1
    assert history[0].accuracy_metrics.sample_count == 2
    assert history[0].sharpe_ratio == pytest.approx(result.sharpe_ratio)
