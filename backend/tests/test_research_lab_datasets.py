"""Tests for research_lab/datasets/. Uses the real PostgreSQL-backed
Feature Store and DatasetRepository."""
from datetime import datetime, timedelta, timezone

import pytest

from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from research_lab.datasets.repository import DatasetRepository
from research_lab.datasets.service import DatasetService

_SYMBOL = "DSTESTX"


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (_SYMBOL,))
    finally:
        fs.offline_store._pool.putconn(conn)
    fs.online_store._client.delete(f"feature_store:{_SYMBOL}:feat_x")


@pytest.fixture
def service(feature_store):
    repo = DatasetRepository()
    svc = DatasetService(feature_store=feature_store, repository=repo)
    yield svc
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM research_dataset_definitions WHERE name = 'test-dataset'")
    finally:
        repo._pool.putconn(conn)


def test_define_persists_and_returns_an_id(service):
    now = datetime.now(timezone.utc)
    definition = service.define("test-dataset", [_SYMBOL], ["feat_x"], now - timedelta(days=10), now)
    assert definition.id is not None


def test_get_definition_round_trips(service):
    now = datetime.now(timezone.utc)
    definition = service.define("test-dataset", [_SYMBOL], ["feat_x"], now - timedelta(days=10), now)
    fetched = service.get_definition(definition.id)
    assert fetched.name == "test-dataset"
    assert fetched.symbols == [_SYMBOL]


def test_build_rebuilds_from_feature_store(service, feature_store):
    now = datetime.now(timezone.utc)
    for i in range(3):
        feature_store.write_feature(
            FeatureValue(symbol=_SYMBOL, feature_name="feat_x", value=float(i), event_timestamp=now - timedelta(days=3 - i))
        )
    definition = service.define("test-dataset", [_SYMBOL], ["feat_x"], now - timedelta(days=10), now)
    dataframe = service.build(definition.id)
    assert len(dataframe) == 3
    assert list(dataframe["value"]) == [0.0, 1.0, 2.0]


def test_build_raises_for_unknown_definition(service):
    with pytest.raises(ValueError):
        service.build(999999999)


def test_list_definitions_includes_created(service):
    now = datetime.now(timezone.utc)
    definition = service.define("test-dataset", [_SYMBOL], ["feat_x"], now - timedelta(days=10), now)
    definitions = service.list_definitions()
    assert any(d.id == definition.id for d in definitions)


def test_service_defaults_to_real_dependencies():
    from research_lab.datasets.service import DatasetService as DS
    svc = DS()
    assert isinstance(svc.feature_store, FeatureStoreService)
    assert isinstance(svc.repository, DatasetRepository)
