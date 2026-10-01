"""Tests for ml_training/models.py."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from decision_engine.models import Prediction
from ml_training.models import (
    CalibrationMethod,
    CalibrationResult,
    DatasetType,
    DatasetVersion,
    FeatureCategory,
    FeatureImportanceEntry,
    FeatureVector,
    ImportanceMethod,
    LabelName,
    LabelSet,
    ModelAlgorithm,
    ModelMetrics,
    ModelRegistryEntry,
    OptimizationResult,
    PromotionState,
    TaskType,
    TrainingRun,
    TrainingSample,
    task_type_for_label,
)


def test_dataset_version_rejects_blank_name():
    with pytest.raises(ValidationError):
        DatasetVersion(
            name="  ", dataset_type=DatasetType.TRADER, symbols=["AAPL"], horizons_days=[5],
            feature_names=["rsi_14"], label_names=["direction"],
            start=datetime.now(timezone.utc), end=datetime.now(timezone.utc), row_count=0,
        )


def test_dataset_version_construction():
    version = DatasetVersion(
        name="trader-v1", dataset_type=DatasetType.TRADER, symbols=["AAPL", "MSFT"], horizons_days=[1, 5],
        feature_names=["rsi_14"], label_names=["direction"],
        start=datetime.now(timezone.utc), end=datetime.now(timezone.utc), row_count=100,
    )
    assert version.dataset_type == DatasetType.TRADER
    assert version.row_count == 100


def test_feature_vector_defaults_to_empty():
    vector = FeatureVector(symbol="AAPL", as_of=datetime.now(timezone.utc))
    assert vector.values == {}
    assert vector.categories == {}


def test_feature_vector_with_categories():
    vector = FeatureVector(
        symbol="AAPL", as_of=datetime.now(timezone.utc), values={"rsi_14": 55.0},
        categories={FeatureCategory.TECHNICAL: ["rsi_14"]},
    )
    assert vector.categories[FeatureCategory.TECHNICAL] == ["rsi_14"]


def test_label_set_requires_nonnegative_volatility():
    with pytest.raises(ValidationError):
        LabelSet(
            symbol="AAPL", as_of=datetime.now(timezone.utc), horizon_days=5, direction=Prediction.BUY,
            expected_return=1.0, expected_volatility=-1.0, trend_continuation=True,
            trend_reversal=False, breakout=False, rejection=False,
        )


def test_label_set_requires_positive_horizon():
    with pytest.raises(ValidationError):
        LabelSet(
            symbol="AAPL", as_of=datetime.now(timezone.utc), horizon_days=0, direction=Prediction.HOLD,
            expected_return=0.0, expected_volatility=1.0, trend_continuation=False,
            trend_reversal=False, breakout=False, rejection=False,
        )


def test_training_sample_combines_features_and_labels():
    labels = LabelSet(
        symbol="AAPL", as_of=datetime.now(timezone.utc), horizon_days=5, direction=Prediction.BUY,
        expected_return=2.0, expected_volatility=10.0, trend_continuation=True,
        trend_reversal=False, breakout=False, rejection=False,
    )
    sample = TrainingSample(
        symbol="AAPL", as_of=datetime.now(timezone.utc), horizon_days=5,
        features={"rsi_14": 60.0}, labels=labels,
    )
    assert sample.labels.direction == Prediction.BUY
    assert sample.features["rsi_14"] == 60.0


@pytest.mark.parametrize(
    "label_name,expected",
    [
        (LabelName.DIRECTION, TaskType.CLASSIFICATION),
        (LabelName.TREND_CONTINUATION, TaskType.CLASSIFICATION),
        (LabelName.TREND_REVERSAL, TaskType.CLASSIFICATION),
        (LabelName.BREAKOUT, TaskType.CLASSIFICATION),
        (LabelName.REJECTION, TaskType.CLASSIFICATION),
        (LabelName.EXPECTED_RETURN, TaskType.REGRESSION),
        (LabelName.EXPECTED_VOLATILITY, TaskType.REGRESSION),
    ],
)
def test_task_type_for_label(label_name, expected):
    assert task_type_for_label(label_name) == expected


def test_model_metrics_defaults():
    metrics = ModelMetrics()
    assert metrics.accuracy_metrics is None
    assert metrics.sharpe_ratio == 0.0
    assert metrics.max_drawdown == 0.0


def test_model_metrics_rejects_negative_max_drawdown():
    with pytest.raises(ValidationError):
        ModelMetrics(max_drawdown=-1.0)


def test_calibration_result_construction():
    result = CalibrationResult(
        model_id="lgbm-v1", method=CalibrationMethod.ISOTONIC,
        calibration_error_before=0.2, calibration_error_after=0.05, artifact_path="/tmp/model.pkl",
    )
    assert result.method == CalibrationMethod.ISOTONIC


def test_feature_importance_entry_construction():
    entry = FeatureImportanceEntry(
        model_id="lgbm-v1", feature_name="rsi_14", importance=0.3, method=ImportanceMethod.SHAP,
    )
    assert entry.method == ImportanceMethod.SHAP


def test_optimization_result_construction():
    result = OptimizationResult(
        model_id="lgbm-v1", algorithm=ModelAlgorithm.LIGHTGBM, best_params={"num_leaves": 31.0},
        best_score=0.75, n_trials=50, study_name="lgbm-direction-5d",
    )
    assert result.n_trials == 50


def test_training_run_defaults_to_running_status():
    run = TrainingRun(
        model_id="lgbm-v1", algorithm=ModelAlgorithm.LIGHTGBM, task_type=TaskType.CLASSIFICATION,
        label_name=LabelName.DIRECTION, horizon_days=5,
    )
    assert run.status.value == "running"


def test_model_registry_entry_rejects_blank_engine_name():
    with pytest.raises(ValidationError):
        ModelRegistryEntry(
            model_id="lgbm-v1", algorithm=ModelAlgorithm.LIGHTGBM, version="v1",
            label_name=LabelName.DIRECTION, horizon_days=5, training_date=datetime.now(timezone.utc),
            engine_name="  ", engine_version="v1", artifact_path="/tmp/x.pkl",
        )


def test_model_registry_entry_defaults_to_candidate_state():
    entry = ModelRegistryEntry(
        model_id="lgbm-v1", algorithm=ModelAlgorithm.LIGHTGBM, version="v1",
        label_name=LabelName.DIRECTION, horizon_days=5, training_date=datetime.now(timezone.utc),
        engine_name="MLModel_lgbm_v1", engine_version="v1", artifact_path="/tmp/x.pkl",
    )
    assert entry.promotion_state == PromotionState.CANDIDATE
    assert entry.approved_by is None
