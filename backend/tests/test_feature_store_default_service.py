"""
Tests for feature_store/service.py's `get_default_feature_store_service`
(production audit MEDIUM #5: "3 engines + 1 pipeline" each independently
constructed their own `FeatureStoreService` - own Redis client, own
Postgres connection pool - when not explicitly injected with one).

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
