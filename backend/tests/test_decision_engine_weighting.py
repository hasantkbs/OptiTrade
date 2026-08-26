"""
Tests for decision_engine/weighting.py, using a fake FeatureStoreService
(satisfying feature_store.interfaces' Protocols) to isolate the weight-
lookup logic from real infrastructure.
"""
from datetime import datetime, timezone
from typing import Dict, Optional

from decision_engine.config import DecisionEngineConfig
from decision_engine.weighting import AccuracyWeightProvider
from feature_store.models import FeatureRecord


class FakeFeatureStoreService:
    def __init__(self) -> None:
        self._data: Dict[tuple, FeatureRecord] = {}

    def seed(self, engine_name: str, feature_name: str, value: float) -> None:
        now = datetime.now(timezone.utc)
        self._data[(engine_name, feature_name)] = FeatureRecord(
            symbol=engine_name, feature_name=feature_name, value=value,
            event_timestamp=now, ingestion_timestamp=now,
        )

    def get_latest_feature(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]:
        return self._data.get((symbol, feature_name))


def test_returns_default_weight_when_no_history_exists():
    config = DecisionEngineConfig(default_accuracy_weight=1.0)
    provider = AccuracyWeightProvider(FakeFeatureStoreService(), config)
    assert provider.get_weight("TechnicalEngine") == 1.0


def test_returns_stored_accuracy_when_present():
    store = FakeFeatureStoreService()
    store.seed("TechnicalEngine", "engine_accuracy_score", 0.73)
    config = DecisionEngineConfig()
    provider = AccuracyWeightProvider(store, config)
    assert provider.get_weight("TechnicalEngine") == 0.73


def test_uses_the_configured_feature_name():
    store = FakeFeatureStoreService()
    store.seed("TechnicalEngine", "custom_accuracy_feature", 0.9)
    config = DecisionEngineConfig(accuracy_feature_name="custom_accuracy_feature")
    provider = AccuracyWeightProvider(store, config)
    assert provider.get_weight("TechnicalEngine") == 0.9


def test_uses_the_configured_default_weight():
    config = DecisionEngineConfig(default_accuracy_weight=0.5)
    provider = AccuracyWeightProvider(FakeFeatureStoreService(), config)
    assert provider.get_weight("BrandNewEngine") == 0.5


def test_different_engines_are_independent():
    store = FakeFeatureStoreService()
    store.seed("TechnicalEngine", "engine_accuracy_score", 0.8)
    store.seed("FundamentalEngine", "engine_accuracy_score", 0.4)
    provider = AccuracyWeightProvider(store, DecisionEngineConfig())
    assert provider.get_weight("TechnicalEngine") == 0.8
    assert provider.get_weight("FundamentalEngine") == 0.4
    assert provider.get_weight("NewsEngine") == 1.0  # no history -> default


# ─────────────────────────────────────────────────────────────────────────
# Failure-resilience regression (production audit HIGH #2: "the weight
# lookup call in _decision_stage is the only pipeline stage without
# try/except - a Feature Store/weight lookup failure can turn an
# otherwise successful decision into HTTP 500").
# ─────────────────────────────────────────────────────────────────────────

class _RaisingFeatureStoreService:
    def get_latest_feature(self, symbol: str, feature_name: str):
        raise RuntimeError("feature store unreachable")


def test_get_weight_falls_back_to_default_when_the_feature_store_lookup_raises():
    config = DecisionEngineConfig(default_accuracy_weight=1.0)
    provider = AccuracyWeightProvider(_RaisingFeatureStoreService(), config)
    # Must not raise - degrades to the same "unknown accuracy" default
    # weight used when no history exists yet, rather than propagating
    # the Feature Store failure out of an otherwise-successful vote.
    assert provider.get_weight("TechnicalEngine") == 1.0


def test_get_weight_uses_the_configured_default_when_lookup_raises():
    config = DecisionEngineConfig(default_accuracy_weight=0.42)
    provider = AccuracyWeightProvider(_RaisingFeatureStoreService(), config)
    assert provider.get_weight("TechnicalEngine") == 0.42
