"""
Tests for feature_store/service.py's `get_default_feature_store_service`.

MEDIUM #5 (prior phase) fixed "3 engines + 1 pipeline" each
independently constructing their own `FeatureStoreService` - own Redis
client, own Postgres connection pool - when not explicitly injected
with one.

This phase (resource-lifecycle hardening) found the SAME unfixed
fallback pattern (`feature_store or FeatureStoreService()`) still
present in 10 more classes reachable from main.py's own startup path
(most directly: `model_serving.service.PredictionService`, constructed
internally by `PipelineService` with no `feature_store=` passed
through - so even after MEDIUM #5, a live process still opened a
second independent Redis client + Postgres pool one level deeper than
that fix reached) plus a direct `FeatureStoreService()` call in main.py
itself. All of them now use the same shared default.

Real PostgreSQL/Redis throughout, matching this project's testing
convention. `feature_store.service._default_service` is reset before/
after every test here (via monkeypatch) so this file's own use of the
shared singleton can't leak into other test modules and vice versa.
"""
import threading
import uuid

import pytest

import feature_store.service as feature_store_service_module
from engines.fundamental.feature_adapter import FundamentalFeatureAdapter
from engines.news.feature_adapter import NewsFeatureAdapter
from engines.technical.feature_adapter import TechnicalFeatureAdapter
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from pipeline.config import PipelineConfig
from pipeline.service import PipelineService


@pytest.fixture(autouse=True)
def reset_default_service(monkeypatch):
    monkeypatch.setattr(feature_store_service_module, "_default_service", None)
    yield
    monkeypatch.setattr(feature_store_service_module, "_default_service", None)


def test_repeated_calls_return_the_same_instance():
    first = get_default_feature_store_service()
    second = get_default_feature_store_service()
    assert first is second


def test_concurrent_first_calls_all_resolve_to_the_same_instance():
    results = []
    lock = threading.Lock()

    def _get():
        service = get_default_feature_store_service()
        with lock:
            results.append(service)

    threads = [threading.Thread(target=_get) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 20
    assert all(service is results[0] for service in results)


# ─────────────────────────────────────────────────────────────────────────
# Consolidation: engines/pipeline that don't explicitly inject a
# feature_store now share the one process-wide default instead of each
# opening their own Redis client + Postgres pool.
# ─────────────────────────────────────────────────────────────────────────

def test_technical_and_fundamental_and_news_adapters_share_the_default_service():
    technical = TechnicalFeatureAdapter()
    fundamental = FundamentalFeatureAdapter()
    news = NewsFeatureAdapter()

    assert technical.feature_store is fundamental.feature_store
    assert fundamental.feature_store is news.feature_store
    assert technical.feature_store is get_default_feature_store_service()


def test_pipeline_service_shares_the_default_service_with_the_engines():
    technical = TechnicalFeatureAdapter()
    service = PipelineService(config=PipelineConfig.from_env())
    assert service.feature_store is technical.feature_store
    assert service.pipeline.feature_store is service.feature_store


def test_pipeline_services_own_nested_prediction_service_also_shares_the_default():
    """The gap MEDIUM #5 left: `PipelineService.__init__` constructs
    `model_serving.service.PredictionService()` with no `feature_store=`
    passed through, so even after MEDIUM #5 this nested service opened
    its own independent Redis client + Postgres pool. Fixed by giving
    `PredictionService` the same shared-default fallback as everything
    else."""
    service = PipelineService(config=PipelineConfig.from_env())
    assert service.model_serving.feature_store is get_default_feature_store_service()


# ─────────────────────────────────────────────────────────────────────────
# The second wave: every other production/research/ML-training class
# that independently fell back to `FeatureStoreService()` now shares the
# same process-wide default instead.
# ─────────────────────────────────────────────────────────────────────────

def test_decision_engine_shares_the_default_service():
    from decision_engine.service import DecisionEngine
    assert DecisionEngine().feature_store is get_default_feature_store_service()


def test_weight_calculator_shares_the_default_service():
    from learning.weighting import WeightCalculator
    assert WeightCalculator().feature_store is get_default_feature_store_service()


def test_technical_alert_evaluator_shares_the_default_service():
    from watchlist.technical_alerts import TechnicalAlertEvaluator
    assert TechnicalAlertEvaluator().feature_store is get_default_feature_store_service()


def test_alert_engine_shares_the_default_service_through_its_technical_evaluator():
    """`watchlist.scheduler.AlertScheduler` (constructed at main.py
    startup) builds `AlertEngine()` with no evaluator injected, which
    in turn builds `TechnicalAlertEvaluator()` with no feature_store
    injected - the chain a live process actually exercises."""
    from watchlist.alert_engine import AlertEngine
    assert AlertEngine().technical_evaluator.feature_store is get_default_feature_store_service()


def test_market_dashboard_service_shares_the_default_service():
    """Constructed directly in main.py's startup_event."""
    from dashboard.market_dashboard import MarketDashboardService
    assert MarketDashboardService()._feature_store is get_default_feature_store_service()


def test_model_dashboard_service_shares_the_default_service():
    """Constructed directly in main.py's startup_event."""
    from dashboard.model_dashboard import ModelDashboardService
    from dashboard.repository import DashboardRepository

    repository = DashboardRepository()
    try:
        assert ModelDashboardService(repository)._feature_store is get_default_feature_store_service()
    finally:
        repository.close()


def test_prediction_service_shares_the_default_service():
    from model_serving.service import PredictionService
    assert PredictionService().feature_store is get_default_feature_store_service()


def test_research_lab_dataset_service_shares_the_default_service():
    from research_lab.datasets.service import DatasetService
    assert DatasetService().feature_store is get_default_feature_store_service()


def test_research_lab_feature_analysis_service_shares_the_default_service():
    from research_lab.feature_analysis.service import FeatureAnalysisService
    assert FeatureAnalysisService().feature_store is get_default_feature_store_service()


def test_ml_training_feature_extractor_shares_the_default_service():
    from ml_training.features.extractor import FeatureExtractor
    assert FeatureExtractor().feature_store is get_default_feature_store_service()


def test_ml_training_feature_importance_service_shares_the_default_service():
    from ml_training.importance.service import FeatureImportanceService
    assert FeatureImportanceService().feature_store is get_default_feature_store_service()


# ─────────────────────────────────────────────────────────────────────────
# Isolation: a caller that explicitly injects its OWN FeatureStoreService
# is completely independent of the shared default - closing it must not
# affect (or be affected by) anything using the shared default.
# ─────────────────────────────────────────────────────────────────────────

def test_explicit_injection_is_independent_of_the_shared_default():
    explicit_service = FeatureStoreService()
    adapter = TechnicalFeatureAdapter(feature_store=explicit_service)

    default_service = get_default_feature_store_service()

    assert adapter.feature_store is explicit_service
    assert adapter.feature_store is not default_service


def test_closing_an_explicitly_injected_service_does_not_break_the_shared_default():
    explicit_service = FeatureStoreService()
    TechnicalFeatureAdapter(feature_store=explicit_service)

    # Something else, elsewhere, uses the shared default.
    other_adapter = FundamentalFeatureAdapter()
    default_service = get_default_feature_store_service()
    assert other_adapter.feature_store is default_service

    explicit_service.offline_store.close()  # tear down the UNSHARED instance

    # The shared default (used by other_adapter, and anyone else who
    # never explicitly injected their own) must still work normally.
    assert default_service.offline_store.ping() is True
    assert default_service.online_store.ping() is True


def test_closing_an_explicitly_injected_prediction_service_does_not_break_the_shared_default():
    """Same disposal-isolation guarantee as above, exercised through one
    of the newly-fixed second-wave sites instead of an engine adapter."""
    from model_serving.service import PredictionService

    from decision_engine.service import DecisionEngine

    explicit_service = FeatureStoreService()
    PredictionService(feature_store=explicit_service)

    decision_engine_default_user = DecisionEngine()
    default_service = get_default_feature_store_service()
    assert decision_engine_default_user.feature_store is default_service

    explicit_service.offline_store.close()

    assert default_service.offline_store.ping() is True
    assert default_service.online_store.ping() is True


# ─────────────────────────────────────────────────────────────────────────
# The shared default is still a fully functional, real FeatureStoreService
# ─────────────────────────────────────────────────────────────────────────

def test_shared_default_service_reads_and_writes_real_feature_store_data():
    symbol = f"DEFAULT-SVC-{uuid.uuid4().hex[:12]}"
    service = get_default_feature_store_service()
    try:
        service.write_feature(FeatureValue(symbol=symbol, feature_name="test_feature", value=42.0))
        record = service.get_latest_feature(symbol, "test_feature")
        assert record is not None
        assert record.value == 42.0
    finally:
        conn = service.offline_store._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (symbol,))
        finally:
            service.offline_store._pool.putconn(conn)
        service.online_store._client.delete(f"feature_store:{symbol}:test_feature")


def test_two_independently_constructed_sharing_classes_see_each_others_writes():
    """A write through one consumer of the shared default (e.g. a
    dashboard service) must be visible to another consumer (e.g.
    ml_training's feature extractor) via the SAME connection pool/Redis
    client - proving they are genuinely the same resource, not just
    two objects with equal config."""
    from dashboard.market_dashboard import MarketDashboardService
    from ml_training.features.extractor import FeatureExtractor

    symbol = f"DEFAULT-SVC-XCLASS-{uuid.uuid4().hex[:12]}"
    writer = MarketDashboardService()._feature_store
    reader = FeatureExtractor().feature_store
    try:
        writer.write_feature(FeatureValue(symbol=symbol, feature_name="test_feature", value=7.5))
        record = reader.get_latest_feature(symbol, "test_feature")
        assert record is not None
        assert record.value == 7.5
    finally:
        conn = reader.offline_store._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (symbol,))
        finally:
            reader.offline_store._pool.putconn(conn)
        reader.online_store._client.delete(f"feature_store:{symbol}:test_feature")


def test_shared_default_services_redis_client_still_has_the_configured_socket_timeout():
    """The explicit Redis socket/connect timeout introduced in commit
    8dde4be (core.infra_config.redis_socket_timeout_seconds) must
    survive this refactor unchanged - RedisOnlineStore itself wasn't
    touched by this phase, but this locks down that the shared default
    every one of these classes now resolves to still gets it."""
    from core.infra_config import redis_socket_timeout_seconds

    service = get_default_feature_store_service()
    kwargs = service.online_store._client.connection_pool.connection_kwargs
    expected = redis_socket_timeout_seconds()
    assert kwargs.get("socket_timeout") == expected
    assert kwargs.get("socket_connect_timeout") == expected
