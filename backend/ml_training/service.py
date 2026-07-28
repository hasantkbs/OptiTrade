"""
OptiTrade ML Training Platform — top-level facade.

`MLTrainingService.run_training_job` is the single entry point that
ties every subpackage (datasets, labels, features, training,
optimization, evaluation, calibration, importance, registry, runs)
together into one full training run, and wires that run into Research
Lab exactly as requirement 13 specifies: every run creates an
experiment (with a written hypothesis), and on completion produces a
benchmark, resolves the hypothesis (ACCEPTED/REJECTED/INCONCLUSIVE),
and generates an experiment-summary report - all via Research Lab's
own, already-existing services, never re-implemented here. The
resulting model is registered in `ml_training.registry` as CANDIDATE
only; shadow deployment (`ml_training.shadow`) and promotion to ACTIVE
are always separate, explicit, human-approved steps.

Mirrors the dependency-injectable facade pattern established by
`research_lab.service.ResearchLabService` and
`learning.service.LearningService`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.models import Prediction
from learning.models import RollingWindow
from ml_training.calibration.service import CalibrationService
from ml_training.config import MLTrainingConfig
from ml_training.datasets.service import DatasetService
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.exceptions import InsufficientDataError
from ml_training.importance.service import FeatureImportanceService
from ml_training.models import (
    CalibrationMethod,
    DatasetType,
    LabelName,
    ModelAlgorithm,
    ModelMetrics,
    ModelRegistryEntry,
    PromotionState,
    TaskType,
    TrainingRun,
    TrainingSample,
    task_type_for_label,
)
from ml_training.optimization.service import OptimizationService
from ml_training.registry.service import ModelRegistryService
from ml_training.runs.service import TrainingRunService
from ml_training.training.base import BaseTrainer
from ml_training.training.service import create_trainer
from research_lab.benchmarking.service import BenchmarkService
from research_lab.experiments.service import ExperimentService
from research_lab.hypothesis.service import HypothesisRegistry
from research_lab.models import Experiment, ExperimentStatus, HypothesisOutcome, Report
from research_lab.reports.service import ReportService

logger = logging.getLogger(__name__)

_BOOLEAN_LABELS = {
    LabelName.TREND_CONTINUATION, LabelName.TREND_REVERSAL, LabelName.BREAKOUT, LabelName.REJECTION,
}

# `model_id` is written as a `symbol` value by
# `ml_training.importance.service.FeatureImportanceService` - both
# `feature_store_records.symbol` and `research_feature_importance.symbol`
# are VARCHAR(32) in the already-existing, frozen schema, so the
# generated id must always fit in 32 characters regardless of which
# algorithm/label/horizon produced it. Short, fixed-width codes (rather
# than the enums' own `.value` strings, some of which are 18+ characters
# long) keep every combination well under that limit.
_ALGORITHM_CODES = {
    ModelAlgorithm.LIGHTGBM: "lgb",
    ModelAlgorithm.XGBOOST: "xgb",
    ModelAlgorithm.CATBOOST: "cat",
    ModelAlgorithm.RANDOM_FOREST: "rf",
}
_LABEL_CODES = {
    LabelName.DIRECTION: "dir",
    LabelName.EXPECTED_RETURN: "eret",
    LabelName.EXPECTED_VOLATILITY: "evol",
    LabelName.TREND_CONTINUATION: "tcon",
    LabelName.TREND_REVERSAL: "trev",
    LabelName.BREAKOUT: "brk",
    LabelName.REJECTION: "rej",
}


def _generate_model_id(algorithm: ModelAlgorithm, label_name: LabelName, horizon_days: int) -> str:
    model_id = f"{_ALGORITHM_CODES[algorithm]}-{_LABEL_CODES[label_name]}-{horizon_days}d-{uuid.uuid4().hex[:8]}"
    assert len(model_id) <= 32, f"model_id {model_id!r} exceeds the 32-char feature_store symbol limit"
    return model_id


class TrainingJobResult:
    """Everything one `run_training_job` call produced, gathered in one
    place for a caller (an admin endpoint, a CLI command) to inspect."""

    def __init__(
        self,
        experiment: Experiment,
        training_run: TrainingRun,
        registry_entry: ModelRegistryEntry,
        metrics: ModelMetrics,
        hypothesis_outcome: HypothesisOutcome,
        report: Report,
    ) -> None:
        self.experiment = experiment
        self.training_run = training_run
        self.registry_entry = registry_entry
        self.metrics = metrics
        self.hypothesis_outcome = hypothesis_outcome
        self.report = report


def _label_value(sample: TrainingSample, label_name: LabelName):
    labels = sample.labels
    if label_name == LabelName.DIRECTION:
        return labels.direction.value
    if label_name == LabelName.EXPECTED_RETURN:
        return labels.expected_return
    if label_name == LabelName.EXPECTED_VOLATILITY:
        return labels.expected_volatility
    if label_name == LabelName.TREND_CONTINUATION:
        return labels.trend_continuation
    if label_name == LabelName.TREND_REVERSAL:
        return labels.trend_reversal
    if label_name == LabelName.BREAKOUT:
        return labels.breakout
    if label_name == LabelName.REJECTION:
        return labels.rejection
    raise ValueError(f"unknown label_name {label_name!r}")


def _samples_to_arrays(
    samples: List[TrainingSample], feature_names: List[str], label_name: LabelName,
) -> Tuple[np.ndarray, np.ndarray, List[float]]:
    X = np.array([[sample.features.get(name, 0.0) for name in feature_names] for sample in samples])
    y = np.array([_label_value(sample, label_name) for sample in samples])
    returns = [sample.labels.expected_return for sample in samples]
    return X, y, returns


def _select_mask(label_name: LabelName, predictions: np.ndarray) -> np.ndarray:
    """Which test samples the model effectively "acted on" - used only
    to build the two return series `research_lab.benchmarking`
    compares. DIRECTION uses BUY calls; the boolean pattern labels use
    a positive (True) call; the two regression labels use a positive
    predicted value."""
    if label_name == LabelName.DIRECTION:
        return predictions == Prediction.BUY.value
    if label_name in _BOOLEAN_LABELS:
        return predictions.astype(bool)
    return predictions.astype(float) > 0


def _resolve_hypothesis_outcome(
    metrics: ModelMetrics, test_sample_count: int, config: MLTrainingConfig,
) -> Tuple[HypothesisOutcome, List[str]]:
    evidence = [
        f"test_sample_count={test_sample_count}", f"expected_value={metrics.expected_value:.4f}",
        f"sharpe_ratio={metrics.sharpe_ratio:.4f}",
    ]
    if test_sample_count < max(10, config.min_training_samples // 5):
        return HypothesisOutcome.INCONCLUSIVE, evidence + ["too few test samples to draw a conclusion"]
    if metrics.expected_value > 0 and metrics.sharpe_ratio > 0:
        return HypothesisOutcome.ACCEPTED, evidence + ["positive expected value and Sharpe ratio on the test set"]
    return HypothesisOutcome.REJECTED, evidence + ["non-positive expected value or Sharpe ratio on the test set"]


class MLTrainingService:
    """Dependency-injectable facade over the whole ML Training Platform."""

    def __init__(
        self,
        datasets: Optional[DatasetService] = None,
        optimization: Optional[OptimizationService] = None,
        evaluation: Optional[ModelEvaluator] = None,
        calibration: Optional[CalibrationService] = None,
        importance: Optional[FeatureImportanceService] = None,
        registry: Optional[ModelRegistryService] = None,
        runs: Optional[TrainingRunService] = None,
        experiments: Optional[ExperimentService] = None,
        hypothesis: Optional[HypothesisRegistry] = None,
        benchmarking: Optional[BenchmarkService] = None,
        reports: Optional[ReportService] = None,
        config: Optional[MLTrainingConfig] = None,
    ) -> None:
        self.config = config or MLTrainingConfig.from_env()
        self.datasets = datasets or DatasetService(config=self.config)
        self.optimization = optimization or OptimizationService(config=self.config)
        self.evaluation = evaluation or ModelEvaluator(config=self.config)
        self.calibration = calibration or CalibrationService(config=self.config)
        self.importance = importance or FeatureImportanceService(config=self.config)
        self.registry = registry or ModelRegistryService()
        self.runs = runs or TrainingRunService()
        self.hypothesis = hypothesis or HypothesisRegistry()
        self.experiments = experiments or ExperimentService(hypothesis_registry=self.hypothesis)
        self.benchmarking = benchmarking or BenchmarkService()
        self.reports = reports or ReportService()

    def run_training_job(
        self,
        author: str,
        symbols: List[str],
        dataset_type: DatasetType,
        label_name: LabelName,
        horizon_days: int,
        algorithm: ModelAlgorithm,
        start: datetime,
        end: datetime,
        engine_version: str = "v1",
        optimize_hyperparameters: bool = False,
        n_trials: Optional[int] = None,
    ) -> TrainingJobResult:
        task_type = task_type_for_label(label_name)
        model_id = _generate_model_id(algorithm, label_name, horizon_days)

        experiment = self.experiments.create(
            name=f"ml_training:{label_name.value}:{horizon_days}d:{algorithm.value}:{model_id}",
            author=author,
            hypothesis_statement=(
                f"A {algorithm.value} model trained on the {label_name.value!r} label "
                f"(horizon={horizon_days}d, dataset_type={dataset_type.value}) has positive "
                f"expected value and Sharpe ratio on held-out data."
            ),
        )
        experiment = self.experiments.transition(experiment.id, ExperimentStatus.RUNNING)

        run: Optional[TrainingRun] = None
        try:
            samples, dataset_version = self.datasets.build_and_save(
                symbols, dataset_type, start, end, horizons_days=[horizon_days],
            )
            if len(samples) < self.config.min_training_samples:
                raise InsufficientDataError(
                    f"only {len(samples)} samples built (need at least "
                    f"{self.config.min_training_samples}) for {label_name.value}/{horizon_days}d"
                )

            run = self.runs.start(
                model_id, algorithm, task_type, label_name, horizon_days, dataset_version.id, experiment.id,
            )

            feature_names = dataset_version.feature_names
            X_train, X_val, X_test, y_train, y_val, y_test, returns_test = self._time_split(
                samples, feature_names, label_name,
            )

            os.makedirs(self.config.model_artifact_dir, exist_ok=True)
            artifact_path = os.path.join(self.config.model_artifact_dir, f"{model_id}.joblib")

            if optimize_hyperparameters:
                _optimization_result, trainer = self.optimization.optimize_and_save(
                    model_id, algorithm, task_type, feature_names, X_train, y_train, X_val, y_val,
                    artifact_path, n_trials=n_trials,
                )
            else:
                trainer = create_trainer(algorithm, task_type, feature_names, config=self.config)
                trainer.fit(X_train, y_train, X_val, y_val)
                trainer.save(artifact_path)

            metrics = self.evaluation.evaluate(trainer, X_test, y_test, actual_returns=returns_test)

            # A held-out validation split that ends up with only one
            # observed class, or a class with just a single member
            # (small or heavily skewed datasets), can't be calibrated -
            # scikit-learn's CalibratedClassifierCV needs at least two
            # classes, each with at least two members, for its internal
            # cross-validation - so calibration is skipped rather than
            # failing the whole run over what is otherwise a
            # successfully trained, evaluated, and registered model.
            _, val_class_counts = np.unique(y_val, return_counts=True)
            if task_type == TaskType.CLASSIFICATION and len(val_class_counts) >= 2 and val_class_counts.min() >= 2:
                self.calibration.calibrate_and_save(
                    model_id, trainer, X_val, y_val, X_test, y_test, CalibrationMethod.ISOTONIC,
                    os.path.join(self.config.model_artifact_dir, f"{model_id}-calibrated.joblib"),
                )

            background_size = min(100, len(X_train))
            self.importance.compute_and_persist_shap(model_id, trainer, X_train[:background_size])

            run = self.runs.complete(run, trainer.hyperparameters, metrics, feature_names, artifact_path)

            registry_entry = self.registry.register(
                ModelRegistryEntry(
                    model_id=model_id, algorithm=algorithm, version="v1", dataset_id=dataset_version.id,
                    hyperparameters=trainer.hyperparameters, metrics=metrics, feature_list=feature_names,
                    label_name=label_name, horizon_days=horizon_days,
                    training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
                    engine_name=f"MLModel:{model_id}", engine_version=engine_version, artifact_path=artifact_path,
                )
            )

            predictions_test = trainer.predict(X_test)
            selected_mask = _select_mask(label_name, predictions_test)
            selected_returns = [value for value, selected in zip(returns_test, selected_mask) if selected]
            self.benchmarking.compare_models(
                f"{model_id}:selected", selected_returns, f"{model_id}:baseline", returns_test,
                RollingWindow.LIFETIME, experiment_id=experiment.id,
            )

            outcome, evidence = _resolve_hypothesis_outcome(metrics, len(y_test), self.config)
            if experiment.hypothesis_id is not None:
                self.hypothesis.resolve(experiment.hypothesis_id, outcome, evidence)
            experiment = self.experiments.transition(experiment.id, ExperimentStatus.COMPLETED)

            report = self.reports.generate_experiment_summary(experiment.id)
        except Exception:
            if run is not None:
                self.runs.fail(run)
            self.experiments.transition(experiment.id, ExperimentStatus.ARCHIVED)
            raise

        log_event(
            logger, component="ml_training", module="ml_training.service", operation="run_training_job",
            status=STATUS_SUCCESS, model_id=model_id, experiment_id=experiment.id,
            hypothesis_outcome=outcome.value,
        )
        return TrainingJobResult(experiment, run, registry_entry, metrics, outcome, report)

    def _time_split(
        self, samples: List[TrainingSample], feature_names: List[str], label_name: LabelName,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[float]]:
        """Chronological train/val/test split (never random) - avoids
        leaking a later-in-time sample into training while an earlier
        one sits in the test set, which a random split over overlapping
        horizon windows could otherwise do."""
        ordered = sorted(samples, key=lambda sample: sample.as_of)
        n = len(ordered)
        n_test = max(1, int(n * self.config.test_size))
        n_val = max(1, int(n * self.config.validation_size))

        train_samples = ordered[: n - n_val - n_test]
        val_samples = ordered[n - n_val - n_test : n - n_test]
        test_samples = ordered[n - n_test :]

        X_train, y_train, _ = _samples_to_arrays(train_samples, feature_names, label_name)
        X_val, y_val, _ = _samples_to_arrays(val_samples, feature_names, label_name)
        X_test, y_test, returns_test = _samples_to_arrays(test_samples, feature_names, label_name)
        return X_train, X_val, X_test, y_train, y_val, y_test, returns_test
