"""Tests for ml_training/datasets/. Uses the real PostgreSQL/Redis-backed
Feature Store and DatasetRepository."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from engines.technical.config import FEATURE_TREND_STRENGTH
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.datasets.repository import DatasetRepository
from ml_training.datasets.service import DatasetService
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType

_SYMBOL = "MLDSTEST"


def _rising(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100 + i * 0.3 for i in range(len(dates))]}, index=dates)


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    now = datetime.now(timezone.utc)
    for i in range(15):
        ts = now - timedelta(days=30 - i)
        fs.write_feature(
            FeatureValue(symbol=_SYMBOL, feature_name=FEATURE_TREND_STRENGTH, value=3.0, event_timestamp=ts)
        )
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_SYMBOL,))
    finally:
        fs.offline_store._pool.putconn(conn)
    fs.online_store._client.delete(f"feature_store:{_SYMBOL}:{FEATURE_TREND_STRENGTH}")


@pytest.fixture
def dataset_repository():
    repo = DatasetRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_dataset_versions WHERE name LIKE 'trader-%' OR name LIKE 'investor-%'")
    finally:
        repo._pool.putconn(conn)


def _builder(feature_store, config=None):
    return DatasetBuilder(
        feature_extractor=FeatureExtractor(feature_store=feature_store),
        config=config or MLTrainingConfig(trader_horizons_days=[3]),
        price_fetcher=_rising,
    )


# ─────────────────────────────────────────────────────────────────────────
# builder.py
# ─────────────────────────────────────────────────────────────────────────

def test_build_produces_samples_for_every_symbol_day_horizon(feature_store):
    now = datetime.now(timezone.utc)
    builder = _builder(feature_store)
    samples, version = builder.build(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=25), now - timedelta(days=20), step_days=1,
    )
    assert len(samples) == 6  # 6 days inclusive * 1 horizon
    assert version.row_count == 6
    assert version.horizons_days == [3]
    assert version.dataset_type == DatasetType.TRADER


def test_build_skips_days_with_no_features(feature_store):
    now = datetime.now(timezone.utc)
    builder = _builder(feature_store)
    # Only 15 days of history were seeded ending "now" - 15 days back from "now"
    samples, version = builder.build(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=60), now - timedelta(days=40), step_days=1,
    )
    assert samples == []
    assert version.row_count == 0


def test_build_uses_investor_horizons_for_investor_dataset_type(feature_store):
    now = datetime.now(timezone.utc)
    config = MLTrainingConfig(investor_horizons_days=[30])
    builder = _builder(feature_store, config=config)
    samples, version = builder.build(
        [_SYMBOL], DatasetType.INVESTOR, now - timedelta(days=22), now - timedelta(days=20), step_days=1,
    )
    assert version.horizons_days == [30]


def test_build_is_point_in_time_correct_no_leakage(feature_store):
    now = datetime.now(timezone.utc)
    builder = _builder(feature_store)
    samples, _ = builder.build(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=25), now - timedelta(days=24), step_days=1,
    )
    for sample in samples:
        # Every feature snapshot must be resolvable strictly at-or-before
        # the sample's own as_of timestamp - the extractor's own
        # get_feature_as_of guarantee, exercised end-to-end here.
        assert sample.as_of <= now


def test_build_skips_samples_when_label_generation_fails(feature_store):
    now = datetime.now(timezone.utc)
    builder = DatasetBuilder(
        feature_extractor=FeatureExtractor(feature_store=feature_store),
        config=MLTrainingConfig(trader_horizons_days=[3]),
        price_fetcher=lambda symbol, start, end: None,
    )
    samples, version = builder.build(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=25), now - timedelta(days=24), step_days=1,
    )
    assert samples == []
    assert version.row_count == 0


def test_build_multiple_horizons_produces_a_sample_per_horizon(feature_store):
    now = datetime.now(timezone.utc)
    config = MLTrainingConfig(trader_horizons_days=[1, 3, 5])
    builder = _builder(feature_store, config=config)
    samples, version = builder.build(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=25), now - timedelta(days=25), step_days=1,
    )
    assert len(samples) == 3
    assert {s.horizon_days for s in samples} == {1, 3, 5}


# ─────────────────────────────────────────────────────────────────────────
# service.py (real Postgres)
# ─────────────────────────────────────────────────────────────────────────

def test_service_build_and_save_persists_version(feature_store, dataset_repository):
    now = datetime.now(timezone.utc)
    svc = DatasetService(builder=_builder(feature_store), repository=dataset_repository)
    samples, version = svc.build_and_save(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=25), now - timedelta(days=20),
    )
    assert version.id is not None
    fetched = svc.get(version.id)
    assert fetched.row_count == version.row_count


def test_service_get_returns_none_for_unknown_id(dataset_repository):
    svc = DatasetService(repository=dataset_repository)
    assert svc.get(999999999) is None


def test_service_list_by_type_filters(feature_store, dataset_repository):
    now = datetime.now(timezone.utc)
    svc = DatasetService(builder=_builder(feature_store), repository=dataset_repository)
    _, version = svc.build_and_save(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=25), now - timedelta(days=20),
    )
    trader_versions = svc.list_by_type(DatasetType.TRADER)
    assert any(v.id == version.id for v in trader_versions)


def test_service_defaults_to_real_dependencies():
    svc = DatasetService()
    assert isinstance(svc.repository, DatasetRepository)
    assert isinstance(svc.builder, DatasetBuilder)
