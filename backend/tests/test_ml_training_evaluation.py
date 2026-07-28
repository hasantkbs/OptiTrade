"""Tests for ml_training/evaluation/."""
import numpy as np
import pytest

from ml_training.config import MLTrainingConfig
from ml_training.evaluation import metrics as metrics_module
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.models import ModelAlgorithm, TaskType
from ml_training.training.service import create_trainer

_FEATURE_NAMES = ["f0", "f1", "f2", "f3", "f4"]


@pytest.fixture(scope="module")
def classifier():
    rng = np.random.RandomState(0)
    X = rng.rand(300, 5)
    y = (X[:, 0] + X[:, 1] > 1).astype(int)
    trainer = create_trainer(ModelAlgorithm.LIGHTGBM, TaskType.CLASSIFICATION, _FEATURE_NAMES, {"n_estimators": 30})
    trainer.fit(X[:250], y[:250])
    return trainer, X[250:], y[250:]


@pytest.fixture(scope="module")
def regressor():
    rng = np.random.RandomState(1)
    X = rng.rand(300, 5)
    y = X[:, 0] * 10 + rng.randn(300) * 0.1
    trainer = create_trainer(ModelAlgorithm.XGBOOST, TaskType.REGRESSION, _FEATURE_NAMES, {"n_estimators": 30})
    trainer.fit(X[:250], y[:250])
    return trainer, X[250:], y[250:]


# ─────────────────────────────────────────────────────────────────────────
# metrics.py (pure)
# ─────────────────────────────────────────────────────────────────────────

def test_classification_metrics_bounded_between_zero_and_one():
    y_true = np.array([0, 1, 1, 0, 1])
    y_pred = np.array([0, 1, 0, 0, 1])
    result = metrics_module.classification_metrics(y_true, y_pred)
    for key in ("accuracy", "precision", "recall", "f1"):
        assert 0.0 <= result[key] <= 1.0


def test_classification_metrics_includes_calibration_and_auc_with_proba():
    y_true = np.array([0, 1, 1, 0])
    y_pred = np.array([0, 1, 1, 0])
    y_proba = np.array([[0.9, 0.1], [0.2, 0.8], [0.1, 0.9], [0.8, 0.2]])
    result = metrics_module.classification_metrics(y_true, y_pred, y_proba)
    assert "calibration_error" in result
    assert "roc_auc" in result
    assert result["roc_auc"] == pytest.approx(1.0)


def test_classification_metrics_roc_auc_for_three_classes():
    # Direction labels are BUY/HOLD/SELL (three classes) - roc_auc must
    # use the multi-class one-vs-rest path, not just the binary path.
    y_true = np.array([0, 1, 2, 0, 1, 2])
    y_pred = np.array([0, 1, 2, 0, 1, 2])
    y_proba = np.array([
        [0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8],
        [0.7, 0.2, 0.1], [0.2, 0.7, 0.1], [0.1, 0.2, 0.7],
    ])
    result = metrics_module.classification_metrics(y_true, y_pred, y_proba)
    assert result["roc_auc"] == pytest.approx(1.0)


def test_calibration_error_from_predictions_perfect_confidence():
    y_true = np.array([1, 1, 1])
    y_proba = np.array([[0.0, 1.0]] * 3)
    error = metrics_module.calibration_error_from_predictions(y_true, y_proba)
    assert error == pytest.approx(0.0)


def test_regression_metrics_returns_mae_and_rmse():
    y_true = np.array([1.0, 2.0, 3.0])
    y_pred = np.array([1.5, 2.0, 2.5])
    result = metrics_module.regression_metrics(y_true, y_pred)
    assert result["mae"] == pytest.approx(1 / 3)
    assert result["rmse"] > 0


def test_profit_factor_all_gains_is_capped():
    assert metrics_module.profit_factor([1.0, 2.0, 3.0]) == 10.0


def test_profit_factor_no_returns_is_zero():
    assert metrics_module.profit_factor([]) == 0.0


def test_profit_factor_mixed_returns():
    result = metrics_module.profit_factor([10.0, -5.0])
    assert result == pytest.approx(2.0)


def test_trading_performance_metrics_includes_all_fields():
    result = metrics_module.trading_performance_metrics([1.0, 2.0, -1.0, 3.0])
    for key in ("expected_value", "sharpe_ratio", "sortino_ratio", "max_drawdown", "profit_factor"):
        assert key in result


# ─────────────────────────────────────────────────────────────────────────
# evaluator.py
# ─────────────────────────────────────────────────────────────────────────

def test_evaluate_classification_produces_full_metrics(classifier):
    trainer, X_test, y_test = classifier
    evaluator = ModelEvaluator()
    result = evaluator.evaluate(trainer, X_test, y_test)
    assert 0.0 <= result.accuracy <= 1.0
    assert result.roc_auc is not None
    assert result.mae is None


def test_evaluate_regression_produces_full_metrics(regressor):
    trainer, X_test, y_test = regressor
    evaluator = ModelEvaluator()
    result = evaluator.evaluate(trainer, X_test, y_test)
    assert result.mae is not None
    assert result.rmse is not None
    assert result.accuracy == 0.0  # not applicable, default


def test_evaluate_with_actual_returns_computes_trading_metrics(classifier):
    trainer, X_test, y_test = classifier
    evaluator = ModelEvaluator()
    returns = [1.0] * len(y_test)
    result = evaluator.evaluate(trainer, X_test, y_test, actual_returns=returns)
    assert result.sharpe_ratio != 0.0 or result.expected_value != 0.0


def test_evaluate_without_actual_returns_leaves_trading_metrics_at_defaults(classifier):
    trainer, X_test, y_test = classifier
    evaluator = ModelEvaluator()
    result = evaluator.evaluate(trainer, X_test, y_test)
    assert result.sharpe_ratio == 0.0
    assert result.expected_value == 0.0


def test_evaluator_defaults_to_real_config():
    evaluator = ModelEvaluator()
    assert isinstance(evaluator.config, MLTrainingConfig)
