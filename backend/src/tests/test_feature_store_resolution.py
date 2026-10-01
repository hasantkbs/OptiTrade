"""
Tests for feature_store/resolution.py - the staleness-aware "check
Feature Store first, recompute what's missing/stale" orchestration
extracted from engines/technical/feature_adapter.py and
engines/fundamental/feature_adapter.py's previously duplicated
`get_features()` (production audit MEDIUM #3). Real PostgreSQL/Redis
throughout, matching this project's testing convention.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from feature_store.models import FeatureValue
from feature_store.resolution import FeatureResolution, resolve_features
from feature_store.service import FeatureStoreService

_FEATURE_A = "resolution-test-feature-a"
_FEATURE_B = "resolution-test-feature-b"


@pytest.fixture
def feature_store():
    return FeatureStoreService()


@pytest.fixture
def symbol():
    return f"RESOLVE-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def cleanup(feature_store, symbol):
    yield
    conn = feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (symbol,))
    finally:
        feature_store.offline_store._pool.putconn(conn)
    for name in (_FEATURE_A, _FEATURE_B):
        feature_store.online_store._client.delete(f"feature_store:{symbol}:{name}")


def test_all_fresh_never_calls_compute_all(feature_store, symbol):
    now = datetime.now(timezone.utc)
    feature_store.write_feature(FeatureValue(symbol=symbol, feature_name=_FEATURE_A, value=1.0, event_timestamp=now))
    feature_store.write_feature(FeatureValue(symbol=symbol, feature_name=_FEATURE_B, value=2.0, event_timestamp=now))

    def _fail_if_called(_symbol):
        raise AssertionError("compute_all should not be called when every feature is fresh")

    resolution = resolve_features(feature_store, symbol, [_FEATURE_A, _FEATURE_B], 3600.0, _fail_if_called)

    assert isinstance(resolution, FeatureResolution)
    assert set(resolution.from_cache) == {_FEATURE_A, _FEATURE_B}
    assert resolution.computed_fresh == []
    assert resolution.values == {_FEATURE_A: 1.0, _FEATURE_B: 2.0}


def test_stale_feature_is_recomputed(feature_store, symbol):
    stale = datetime.now(timezone.utc) - timedelta(hours=2)
    feature_store.write_feature(
        FeatureValue(symbol=symbol, feature_name=_FEATURE_A, value=1.0, event_timestamp=stale)
    )
    calls = []

    def _compute_all(sym):
        calls.append(sym)
        return {_FEATURE_A: 99.0}

    resolution = resolve_features(feature_store, symbol, [_FEATURE_A], 3600.0, _compute_all)

    assert calls == [symbol]
    assert _FEATURE_A in resolution.computed_fresh
    assert _FEATURE_A not in resolution.from_cache
    assert resolution.values[_FEATURE_A] == 99.0


def test_missing_feature_is_computed(feature_store, symbol):
    resolution = resolve_features(feature_store, symbol, [_FEATURE_A], 3600.0, lambda s: {_FEATURE_A: 5.0})
    assert resolution.computed_fresh == [_FEATURE_A]
    assert resolution.values == {_FEATURE_A: 5.0}


def test_mix_of_cached_and_missing(feature_store, symbol):
    now = datetime.now(timezone.utc)
    feature_store.write_feature(
        FeatureValue(symbol=symbol, feature_name=_FEATURE_A, value=7.0, event_timestamp=now)
    )
    resolution = resolve_features(
        feature_store, symbol, [_FEATURE_A, _FEATURE_B], 3600.0, lambda s: {_FEATURE_B: 8.0},
    )
    assert resolution.from_cache == [_FEATURE_A]
    assert resolution.computed_fresh == [_FEATURE_B]
    assert resolution.values == {_FEATURE_A: 7.0, _FEATURE_B: 8.0}


def test_compute_all_result_missing_a_feature_is_simply_absent(feature_store, symbol):
    resolution = resolve_features(feature_store, symbol, [_FEATURE_A, _FEATURE_B], 3600.0, lambda s: {_FEATURE_A: 1.0})
    assert _FEATURE_A in resolution.values
    assert _FEATURE_B not in resolution.values
    assert _FEATURE_B not in resolution.from_cache
    assert _FEATURE_B not in resolution.computed_fresh


# ─────────────────────────────────────────────────────────────────────────
# No cross-"engine" contamination - two independent callers (standing in
# for the technical and fundamental engines, which use disjoint feature
# name sets against the same Feature Store) never observe each other's
# values, since resolve_features is a pure function keyed only by the
# (symbol, feature_name) pairs it's explicitly given.
# ─────────────────────────────────────────────────────────────────────────

def test_two_independent_callers_do_not_contaminate_each_others_features(feature_store, symbol):
    # compute_all is responsible for its own write-back to the Feature
    # Store, exactly like the real engines' _compute_all methods -
    # resolve_features itself never persists anything.
    def _compute_a(_symbol):
        feature_store.write_feature(FeatureValue(symbol=_symbol, feature_name=_FEATURE_A, value=111.0))
        return {_FEATURE_A: 111.0}

    def _compute_b(_symbol):
        feature_store.write_feature(FeatureValue(symbol=_symbol, feature_name=_FEATURE_B, value=222.0))
        return {_FEATURE_B: 222.0}

    technical_features = [_FEATURE_A]
    fundamental_features = [_FEATURE_B]

    technical_resolution = resolve_features(feature_store, symbol, technical_features, 3600.0, _compute_a)
    fundamental_resolution = resolve_features(feature_store, symbol, fundamental_features, 3600.0, _compute_b)

    assert technical_resolution.values == {_FEATURE_A: 111.0}
    assert fundamental_resolution.values == {_FEATURE_B: 222.0}

    # Re-resolving "technical"'s own features must still see only its own
    # (now-persisted, fresh) value, never the "fundamental" caller's,
    # even though both went through the same shared function against the
    # same Feature Store.
    def _fail_if_called(_symbol):
        raise AssertionError("compute_all should not be called - the value written above is still fresh")

    second_technical_resolution = resolve_features(feature_store, symbol, technical_features, 3600.0, _fail_if_called)
    assert second_technical_resolution.from_cache == [_FEATURE_A]
    assert second_technical_resolution.values == {_FEATURE_A: 111.0}
