"""Tests for scripts/backtest_decision_engine.py's core evaluation loop.
Uses a fake DecisionEngine (never a real decide() call) so this suite
never touches Postgres/Redis - it tests the backtest's OWN logic
(direction-labeling, HOLD exclusion, accuracy/baseline math), not
decision_engine's, which Tasks 1-2's own tests already cover."""
from datetime import datetime, timezone

import pytest

from decision_engine.models import DecisionOutput, Prediction
from scripts.backtest_decision_engine import evaluate_decisions


def _output(decision, day):
    return DecisionOutput(
        symbol="TEST", decision=decision, confidence=0.8, expected_return=0.0,
        expected_volatility=0.0, aggregation_strategy_version="v1",
        data_sufficiency=1.0, evidence=[], engine_results=[], timestamp=day,
    )


def test_evaluate_decisions_excludes_hold_from_accuracy_but_counts_it():
    decisions = [
        (_output(Prediction.BUY, datetime(2025, 1, 1, tzinfo=timezone.utc)), True),   # correct BUY
        (_output(Prediction.HOLD, datetime(2025, 1, 2, tzinfo=timezone.utc)), True),  # abstention - excluded
        (_output(Prediction.SELL, datetime(2025, 1, 3, tzinfo=timezone.utc)), True),  # wrong SELL (actual was up)
    ]
    result = evaluate_decisions(decisions)
    assert result["n_directional_samples"] == 2          # BUY + SELL only, HOLD excluded
    assert result["n_hold"] == 1
    assert result["accuracy"] == pytest.approx(0.5)       # 1 correct of 2 directional


def test_evaluate_decisions_all_hold_reports_zero_directional_samples_not_an_error():
    decisions = [(_output(Prediction.HOLD, datetime(2025, 1, 1, tzinfo=timezone.utc)), True)]
    result = evaluate_decisions(decisions)
    assert result["n_directional_samples"] == 0
    assert result["n_hold"] == 1
    assert result["accuracy"] == 0.0  # honest zero, not a crash/NaN


def test_evaluate_decisions_majority_baseline_matches_actual_distribution():
    decisions = [
        (_output(Prediction.BUY, datetime(2025, 1, 1, tzinfo=timezone.utc)), True),
        (_output(Prediction.BUY, datetime(2025, 1, 2, tzinfo=timezone.utc)), True),
        (_output(Prediction.SELL, datetime(2025, 1, 3, tzinfo=timezone.utc)), False),
    ]
    result = evaluate_decisions(decisions)
    # 2 of 3 actual outcomes were "up" (True) - majority baseline = 2/3
    assert result["majority_baseline"] == pytest.approx(2 / 3)
