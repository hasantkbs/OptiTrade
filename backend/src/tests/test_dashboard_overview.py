"""Tests for dashboard/overview.py. Real PostgreSQL throughout."""
import pytest

from dashboard.overview import OverviewDashboardService
from dashboard.repository import DashboardRepository
from learning.persistence import LearningRepository


@pytest.fixture
def repo():
    repository = DashboardRepository()
    yield repository
    repository.close()


@pytest.fixture
def service(repo):
    return OverviewDashboardService(repo, learning_repository=LearningRepository())


def test_build_returns_all_expected_counts(service):
    metrics = service.build()
    assert metrics.total_users >= 0
    assert metrics.active_users >= 0
    assert metrics.total_portfolios >= 0
    assert metrics.total_watchlists >= 0
    assert metrics.total_alerts >= 0
    assert metrics.total_paper_accounts >= 0
    assert metrics.total_models >= 0
    assert metrics.active_engines >= 0
    assert metrics.learning_status.total_samples >= 0
    assert metrics.generated_at is not None


def test_active_engine_count_defaults_to_learning_engines_tracked(service):
    metrics = service.build()
    assert metrics.active_engines == metrics.learning_status.engines_tracked


class _FakeEngineRegistry:
    def all_enabled(self):
        return ["engine1", "engine2"]


class _FakeModelServing:
    def get_active_engines(self):
        return ["ml_engine1"]


def test_active_engine_count_uses_injected_registry_and_model_serving(repo):
    service = OverviewDashboardService(
        repo, learning_repository=LearningRepository(), engine_registry=_FakeEngineRegistry(),
        model_serving=_FakeModelServing(),
    )
    metrics = service.build()
    assert metrics.active_engines == 3
