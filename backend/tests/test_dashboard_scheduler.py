"""Tests for dashboard/scheduler.py. Real PostgreSQL + real Redis (an
isolated logical DB, matching this project's established convention)."""
import pytest
import redis

from dashboard.config import DashboardConfig
from dashboard.engine_dashboard import EngineDashboardService
from dashboard.market_dashboard import MarketDashboardService
from dashboard.overview import OverviewDashboardService
from dashboard.repository import DashboardRepository
from dashboard.scheduler import DashboardScheduler
from learning.persistence import LearningRepository


@pytest.fixture
def redis_client():
    client = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def repo():
    repository = DashboardRepository()
    yield repository
    repository.close()


@pytest.fixture
def config():
    return DashboardConfig(redis_db=15, overview_cache_ttl_seconds=300, dashboard_cache_ttl_seconds=300)


@pytest.fixture
def scheduler(repo, config, redis_client):
    return DashboardScheduler(
        OverviewDashboardService(repo, learning_repository=LearningRepository()),
        MarketDashboardService(),
        EngineDashboardService(repo),
        redis_client=redis_client, config=config,
    )


def test_refresh_overview_cache_stores_json(scheduler, redis_client):
    metrics = scheduler.refresh_overview_cache()
    cached = redis_client.get("dashboard:overview")
    assert cached is not None
    assert str(metrics.total_users) in cached


def test_get_cached_overview_returns_none_before_refresh(scheduler):
    assert scheduler.get_cached_overview() is None


def test_refresh_market_cache(scheduler):
    scheduler.refresh_market_cache(symbols=["AAPL"])
    assert scheduler.get_cached_market() is not None


def test_refresh_engine_cache(scheduler):
    scheduler.refresh_engine_cache()
    assert scheduler.get_cached_engine() is not None


def test_refresh_all_returns_success_for_every_view(scheduler):
    results = scheduler.refresh_all()
    assert results == {"overview": True, "market": True, "engine": True}


def test_redis_errors_are_caught_not_raised(repo, config):
    class _BrokenRedis:
        def get(self, key):
            raise redis.RedisError("boom")

        def set(self, *args, **kwargs):
            raise redis.RedisError("boom")

    scheduler = DashboardScheduler(
        OverviewDashboardService(repo, learning_repository=LearningRepository()),
        MarketDashboardService(), EngineDashboardService(repo), redis_client=_BrokenRedis(), config=config,
    )
    scheduler.refresh_overview_cache()  # must not raise
    assert scheduler.get_cached_overview() is None
