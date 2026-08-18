"""
Tests proving every `redis.Redis(...)` construction site in this
backend now sets an explicit, operator-configurable socket timeout
(production audit LOW batch: "Add/verify Redis operation timeouts
where absent").

Each test sets REDIS_SOCKET_TIMEOUT_SECONDS to a value (2.5) that does
not coincide with any library-level default, so a passing test proves
the construction site actually threads the configured value through -
not merely that some timeout (possibly an unrelated library default)
happens to be present.

Each service is constructed with its default (no explicit `client=`)
so the real construction code path - the one that matters - runs; no
network I/O happens merely by constructing a `redis.Redis` client.
"""
import pytest

_CONFIGURED_TIMEOUT = 2.5


@pytest.fixture(autouse=True)
def _configured_redis_timeout(monkeypatch):
    monkeypatch.setenv("REDIS_SOCKET_TIMEOUT_SECONDS", str(_CONFIGURED_TIMEOUT))


def _assert_has_the_configured_socket_timeout(client) -> None:
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs.get("socket_timeout") == _CONFIGURED_TIMEOUT
    assert kwargs.get("socket_connect_timeout") == _CONFIGURED_TIMEOUT


def test_feature_store_online_store_client_has_the_configured_socket_timeout():
    from feature_store.online_store import RedisOnlineStore
    _assert_has_the_configured_socket_timeout(RedisOnlineStore()._client)


def test_portfolio_price_service_client_has_the_configured_socket_timeout():
    from portfolio.prices import PriceService
    _assert_has_the_configured_socket_timeout(PriceService()._client)


def test_users_session_service_client_has_the_configured_socket_timeout():
    from users.repository import UsersRepository
    from users.sessions import SessionService
    _assert_has_the_configured_socket_timeout(SessionService(UsersRepository())._client)


def test_model_serving_metadata_cache_client_has_the_configured_socket_timeout():
    from model_serving.cache import ModelMetadataCache
    _assert_has_the_configured_socket_timeout(ModelMetadataCache()._client)


def test_dashboard_scheduler_client_has_the_configured_socket_timeout():
    from dashboard.engine_dashboard import EngineDashboardService
    from dashboard.market_dashboard import MarketDashboardService
    from dashboard.overview import OverviewDashboardService
    from dashboard.repository import DashboardRepository
    from dashboard.scheduler import DashboardScheduler

    repository = DashboardRepository()
    try:
        scheduler = DashboardScheduler(
            OverviewDashboardService(repository), MarketDashboardService(), EngineDashboardService(repository),
        )
        _assert_has_the_configured_socket_timeout(scheduler._client)
    finally:
        repository.close()


def test_watchlist_news_alert_evaluator_client_has_the_configured_socket_timeout():
    from watchlist.news_alerts import NewsAlertEvaluator
    _assert_has_the_configured_socket_timeout(NewsAlertEvaluator()._redis_client)


def test_default_socket_timeout_is_five_seconds_when_unconfigured(monkeypatch):
    monkeypatch.delenv("REDIS_SOCKET_TIMEOUT_SECONDS", raising=False)
    from portfolio.prices import PriceService
    kwargs = PriceService()._client.connection_pool.connection_kwargs
    assert kwargs.get("socket_timeout") == 5.0
    assert kwargs.get("socket_connect_timeout") == 5.0
