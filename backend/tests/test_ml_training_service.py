"""Tests for ml_training/service.py — the top-level facade wiring every
subpackage together into one full training run. Real PostgreSQL/Redis
throughout; the Feature Store is seeded with real values and price data
comes from an injected deterministic synthetic fetcher (matching
`tests/test_ml_training_datasets.py`'s own pattern) rather than live
network calls, so the test is fast and reproducible."""
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from engines.technical.config import FEATURE_TREND_STRENGTH
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from ml_training.calibration.repository import CalibrationRepository
from ml_training.calibration.service import CalibrationService
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.datasets.repository import DatasetRepository
from ml_training.datasets.service import DatasetService
from ml_training.exceptions import InsufficientDataError
from ml_training.features.extractor import FeatureExtractor
from ml_training.importance.service import FeatureImportanceService
from ml_training.models import DatasetType, LabelName, ModelAlgorithm, PromotionState
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.registry.service import ModelRegistryService
from ml_training.runs.repository import TrainingRunRepository
from ml_training.runs.service import TrainingRunService
from ml_training.service import MLTrainingService
from research_lab.benchmarking.repository import BenchmarkRepository
from research_lab.benchmarking.service import BenchmarkService
from research_lab.experiments.repository import ExperimentRepository
from research_lab.experiments.service import ExperimentService
from research_lab.feature_analysis.service import FeatureAnalysisService
from research_lab.hypothesis.repository import HypothesisRepository
from research_lab.hypothesis.service import HypothesisRegistry
from research_lab.models import ExperimentStatus, HypothesisOutcome
from research_lab.reports.repository import ReportRepository
from research_lab.reports.service import ReportService

_SYMBOL = "MLSVCTEST"
_AUTHOR = "ml-training-service-test"
_N_DAYS = 30


_PHASE_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _oscillating(symbol, start, end):
    # `generate_labels` calls this per-sample with a *local* window
    # scoped to that sample's own as_of, not the whole dataset's date
    # range - phase must be keyed off an absolute date (days since a
    # fixed epoch), or every call would restart its sine wave at the
    # same index and produce the exact same (single) label every time.
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    prices = [100 + 5 * math.sin((d - _PHASE_EPOCH).days / 3.0) for d in dates]
    return pd.DataFrame({"Close": prices}, index=dates)


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=_N_DAYS)
    for i in range(_N_DAYS):
        ts = start + timedelta(days=i)
        fs.write_feature(FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_TREND_STRENGTH, value=3.0, event_timestamp=ts))
    yield fs, start, now
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_SYMBOL,))
    finally:
        fs.offline_store._pool.putconn(conn)
    fs.online_store._client.delete(f"feature_store:{_SYMBOL}:{FEATURE_TREND_STRENGTH}")


@pytest.fixture
def config():
    return MLTrainingConfig(min_training_samples=10, test_size=0.2, validation_size=0.2, random_state=42)


@pytest.fixture
def service(feature_store, config):
    fs, _start, _now = feature_store
    builder = DatasetBuilder(
        feature_extractor=FeatureExtractor(feature_store=fs), config=config, price_fetcher=_oscillating,
    )
    svc = MLTrainingService(
        datasets=DatasetService(builder=builder, repository=DatasetRepository(), config=config),
        config=config,
    )
    yield svc
    _cleanup(svc)


def _cleanup(svc: MLTrainingService) -> None:
    def _exec(pool, sql, params):
        conn = pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, params)
        finally:
            pool.putconn(conn)

    _exec(svc.experiments.repository._pool, "DELETE FROM research_experiments WHERE author = %s", (_AUTHOR,))
    _exec(
        svc.hypothesis.repository._pool,
        "DELETE FROM research_hypotheses WHERE statement LIKE %s",
        ("A % model trained on%",),
    )
    _exec(svc.registry.repository._pool, "DELETE FROM ml_training_model_registry WHERE engine_name LIKE %s", ("MLModel:%",))
    _exec(svc.runs.repository._pool, "DELETE FROM ml_training_runs WHERE model_id LIKE %s", ("%d-%",))
    _exec(svc.datasets.repository._pool, "DELETE FROM ml_training_dataset_versions WHERE symbols::text LIKE %s", (f"%{_SYMBOL}%",))
    _exec(svc.calibration.repository._pool, "DELETE FROM ml_training_calibration_results WHERE model_id LIKE %s", ("%d-%",))
    _exec(svc.benchmarking.repository._pool, "DELETE FROM research_benchmark_results WHERE subject_a LIKE %s", ("%:selected",))
    _exec(svc.reports.repository._pool, "DELETE FROM research_reports WHERE title LIKE %s", ("Experiment Summary: ml_training:%",))
    _exec(
        svc.importance.feature_analysis_service.repository._pool,
        "DELETE FROM research_feature_importance WHERE engine_name LIKE %s", ("MLModel:%",),
    )
    _exec(svc.importance.feature_store.offline_store._pool, "DELETE FROM feature_store_records WHERE feature_name LIKE %s", ("shap_importance:%",))


def test_run_training_job_end_to_end(service, feature_store):
    _fs, start, now = feature_store
    result = service.run_training_job(
        author=_AUTHOR, symbols=[_SYMBOL], dataset_type=DatasetType.TRADER, label_name=LabelName.DIRECTION,
        horizon_days=1, algorithm=ModelAlgorithm.RANDOM_FOREST, start=start, end=now,
    )

    assert result.experiment.id is not None
    assert result.experiment.status == ExperimentStatus.COMPLETED
    assert result.experiment.author == _AUTHOR

    assert result.training_run.id is not None
    assert result.training_run.status.value == "completed"
    assert result.training_run.dataset_id is not None

    assert result.registry_entry.id is not None
    assert result.registry_entry.promotion_state == PromotionState.CANDIDATE
    assert result.registry_entry.algorithm == ModelAlgorithm.RANDOM_FOREST
    assert result.registry_entry.label_name == LabelName.DIRECTION
    assert len(result.registry_entry.model_id) <= 32

    assert result.hypothesis_outcome in {
        HypothesisOutcome.ACCEPTED, HypothesisOutcome.REJECTED, HypothesisOutcome.INCONCLUSIVE,
    }

    assert result.report.id is not None
    assert result.report.content["experiment_id"] == result.experiment.id
    assert result.report.content["hypothesis"]["outcome"] == result.hypothesis_outcome.value

    # The registry entry is independently readable from a fresh service.
    fetched = service.registry.get(result.registry_entry.model_id)
    assert fetched is not None
    assert fetched.metrics is not None


def test_run_training_job_raises_and_archives_experiment_on_insufficient_data(service, feature_store):
    _fs, start, now = feature_store
    with pytest.raises(InsufficientDataError):
        service.run_training_job(
            author=_AUTHOR, symbols=["MLSVCTEST-NO-SUCH-SYMBOL"], dataset_type=DatasetType.TRADER,
            label_name=LabelName.DIRECTION, horizon_days=1, algorithm=ModelAlgorithm.RANDOM_FOREST,
            start=start, end=now,
        )

    experiments = service.experiments.list_by_status(ExperimentStatus.ARCHIVED, limit=200)
    assert any(experiment.author == _AUTHOR for experiment in experiments)


def test_service_defaults_to_real_dependencies():
    svc = MLTrainingService()
    assert isinstance(svc.registry, ModelRegistryService)
    assert isinstance(svc.runs, TrainingRunService)
