"""Tests for research_lab/feature_analysis/. Uses the real
PostgreSQL-backed Feature Store and FeatureAnalysisRepository."""
from datetime import datetime, timedelta, timezone

import pytest

from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService
from research_lab.feature_analysis import correlation, drift, importance, stability
from research_lab.feature_analysis.repository import FeatureAnalysisRepository
from research_lab.feature_analysis.service import FeatureAnalysisService
from research_lab.config import ResearchLabConfig

_SYMBOL = "FATESTX"


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
    for name in ["feat_a", "feat_b", "feat_c"]:
        fs.online_store._client.delete(f"feature_store:{_SYMBOL}:{name}")


@pytest.fixture
def repository():
    repo = FeatureAnalysisRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM research_feature_importance WHERE symbol = %s", (_SYMBOL,))
            cur.execute("DELETE FROM research_feature_correlation WHERE symbol = %s", (_SYMBOL,))
            cur.execute("DELETE FROM research_feature_stability WHERE symbol = %s", (_SYMBOL,))
            cur.execute("DELETE FROM research_feature_drift WHERE symbol = %s", (_SYMBOL,))
    finally:
        repo._pool.putconn(conn)


def _seed(feature_store, feature_name: str, values, now):
    for i, value in enumerate(values):
        feature_store.write_feature(
            FeatureValue(symbol=_SYMBOL, feature_name=feature_name, value=value, event_timestamp=now - timedelta(days=len(values) - i))
        )


# ─────────────────────────────────────────────────────────────────────────
# importance.py (pure)
# ─────────────────────────────────────────────────────────────────────────

def test_importance_to_records_maps_every_entry():
    records = importance.to_records(_SYMBOL, "TestEngine", {"feat_a": 0.6, "feat_b": 0.4})
    assert len(records) == 2
    assert {r.feature_name for r in records} == {"feat_a", "feat_b"}


def test_importance_to_records_empty_dict():
    assert importance.to_records(_SYMBOL, "TestEngine", {}) == []


# ─────────────────────────────────────────────────────────────────────────
# correlation.py
# ─────────────────────────────────────────────────────────────────────────

def test_correlation_perfectly_correlated_features(feature_store):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0, 2.0, 3.0, 4.0, 5.0], now)
    _seed(feature_store, "feat_b", [2.0, 4.0, 6.0, 8.0, 10.0], now)

    record = correlation.compute_correlation(feature_store, _SYMBOL, "feat_a", "feat_b", now - timedelta(days=10), now)
    assert record.correlation == pytest.approx(1.0, abs=1e-6)


def test_correlation_returns_none_with_insufficient_overlap(feature_store):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0], now)
    record = correlation.compute_correlation(feature_store, _SYMBOL, "feat_a", "feat_c", now - timedelta(days=10), now)
    assert record is None


def test_correlation_zero_when_no_variance(feature_store):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [5.0, 5.0, 5.0], now)
    _seed(feature_store, "feat_b", [1.0, 2.0, 3.0], now)
    record = correlation.compute_correlation(feature_store, _SYMBOL, "feat_a", "feat_b", now - timedelta(days=10), now)
    assert record.correlation == 0.0


# ─────────────────────────────────────────────────────────────────────────
# stability.py
# ─────────────────────────────────────────────────────────────────────────

def test_stability_high_for_constant_feature(feature_store):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [10.0, 10.0, 10.0, 10.0], now)
    record = stability.compute_stability(feature_store, _SYMBOL, "feat_a", now - timedelta(days=10), now)
    assert record.stability_score == 1.0


def test_stability_low_for_wildly_varying_feature(feature_store):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0, 100.0, 1.0, 100.0], now)
    record = stability.compute_stability(feature_store, _SYMBOL, "feat_a", now - timedelta(days=10), now)
    assert record.stability_score < 0.5


def test_stability_none_with_fewer_than_two_values(feature_store):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0], now)
    assert stability.compute_stability(feature_store, _SYMBOL, "feat_a", now - timedelta(days=10), now) is None


# ─────────────────────────────────────────────────────────────────────────
# drift.py
# ─────────────────────────────────────────────────────────────────────────

def test_drift_detected_between_clearly_different_distributions(feature_store):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0] * 10 + [100.0] * 10, now)
    record = drift.compute_drift(
        feature_store, _SYMBOL, "feat_a",
        now - timedelta(days=19), now - timedelta(days=10), now - timedelta(days=9), now,
        ResearchLabConfig(),
    )
    assert record.drifted is True


def test_drift_none_with_insufficient_samples(feature_store):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0], now)
    record = drift.compute_drift(
        feature_store, _SYMBOL, "feat_a", now - timedelta(days=10), now - timedelta(days=5),
        now - timedelta(days=4), now,
    )
    assert record is None


# ─────────────────────────────────────────────────────────────────────────
# service.py (full pipeline, real Postgres)
# ─────────────────────────────────────────────────────────────────────────

def test_service_record_and_retrieve_importance(feature_store, repository):
    svc = FeatureAnalysisService(feature_store=feature_store, repository=repository)
    svc.record_importance(_SYMBOL, "TestEngine", {"feat_a": 0.7, "feat_b": 0.3})
    history = svc.get_importance_history(_SYMBOL, "TestEngine", "feat_a")
    assert len(history) == 1
    assert history[0].importance == 0.7


def test_service_analyze_correlation_persists(feature_store, repository):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0, 2.0, 3.0], now)
    _seed(feature_store, "feat_b", [1.0, 2.0, 3.0], now)
    svc = FeatureAnalysisService(feature_store=feature_store, repository=repository)
    record = svc.analyze_correlation(_SYMBOL, "feat_a", "feat_b", now - timedelta(days=10), now)
    assert record is not None
    assert record.correlation == pytest.approx(1.0)


def test_service_analyze_stability_persists(feature_store, repository):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0, 1.0, 1.0], now)
    svc = FeatureAnalysisService(feature_store=feature_store, repository=repository)
    record = svc.analyze_stability(_SYMBOL, "feat_a", now - timedelta(days=10), now)
    assert record.stability_score == 1.0


def test_service_analyze_drift_persists(feature_store, repository):
    now = datetime.now(timezone.utc)
    _seed(feature_store, "feat_a", [1.0] * 10 + [50.0] * 10, now)
    svc = FeatureAnalysisService(feature_store=feature_store, repository=repository)
    record = svc.analyze_drift(
        _SYMBOL, "feat_a", now - timedelta(days=19), now - timedelta(days=10), now - timedelta(days=9), now,
    )
    assert record is not None


def test_service_defaults_to_real_dependencies():
    svc = FeatureAnalysisService()
    assert isinstance(svc.feature_store, FeatureStoreService)
    assert isinstance(svc.repository, FeatureAnalysisRepository)
