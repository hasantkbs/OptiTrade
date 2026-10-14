"""Unit tests for scripts/train_ml_candidate_us_news_control.py's
significance-test logic (McNemar's test, paired bootstrap) on
synthetic predictions - no model training, no database, no network.
The actual end-to-end run (real training + real held-out data) is
exercised manually, matching this plan's established precedent."""
import sys
sys.path.insert(0, ".")

import numpy as np

from scripts.train_ml_candidate_us_news_control import _bootstrap_gap, _mcnemar_test


# ── _mcnemar_test ────────────────────────────────────────────────────

def test_mcnemar_identical_predictions_give_zero_statistic_and_p_one():
    y_true = np.array([0, 1, 2, 0, 1, 2, 0, 1])
    pred = np.array([0, 1, 2, 1, 0, 2, 0, 0])  # some right, some wrong, identical both arms
    b, c, statistic, p_value = _mcnemar_test(y_true, pred, pred)
    assert b == 0 and c == 0
    assert statistic == 0.0
    assert p_value == 1.0


def test_mcnemar_detects_a_one_sided_advantage():
    y_true = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0])
    pred_a = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 1])  # 9/10 right
    pred_b = np.array([1, 1, 0, 0, 1, 1, 0, 1, 2, 1])  # 5/10 right, wrong exactly where A is right
    b, c, statistic, p_value = _mcnemar_test(y_true, pred_a, pred_b)
    assert b > c  # A right/B wrong happens more often than the reverse
    assert statistic > 0


def test_mcnemar_p_value_is_bounded():
    rng = np.random.default_rng(0)
    y_true = rng.integers(0, 3, size=200)
    pred_a = rng.integers(0, 3, size=200)
    pred_b = rng.integers(0, 3, size=200)
    _, _, _, p_value = _mcnemar_test(y_true, pred_a, pred_b)
    assert 0.0 <= p_value <= 1.0


# ── _bootstrap_gap ──────────────────────────────────────────────────

def test_bootstrap_gap_reports_a_clear_positive_gap_when_one_model_is_strictly_better(capsys):
    rng = np.random.default_rng(1)
    n = 500
    y_true = rng.integers(0, 3, size=n)
    pred_with = y_true.copy()  # perfect
    pred_without = rng.integers(0, 3, size=n)  # random

    def _proba_for(pred, y):
        proba = np.full((n, 3), 0.1)
        proba[np.arange(n), pred] = 0.8
        return proba / proba.sum(axis=1, keepdims=True)

    proba_with = _proba_for(pred_with, y_true)
    proba_without = _proba_for(pred_without, y_true)

    _bootstrap_gap(y_true, pred_with, proba_with, pred_without, proba_without)
    output = capsys.readouterr().out

    assert "Accuracy gap" in output
    assert "ROC-AUC gap" in output
    assert "P(gap <= 0)=0.0000" in output  # the perfect model should never lose a resample


def test_bootstrap_gap_is_reproducible_with_a_fixed_seed(capsys):
    rng = np.random.default_rng(2)
    n = 300
    y_true = rng.integers(0, 3, size=n)
    pred_with = rng.integers(0, 3, size=n)
    pred_without = rng.integers(0, 3, size=n)
    proba_with = np.full((n, 3), 1 / 3)
    proba_without = np.full((n, 3), 1 / 3)

    _bootstrap_gap(y_true, pred_with, proba_with, pred_without, proba_without)
    first = capsys.readouterr().out
    _bootstrap_gap(y_true, pred_with, proba_with, pred_without, proba_without)
    second = capsys.readouterr().out

    assert first == second
