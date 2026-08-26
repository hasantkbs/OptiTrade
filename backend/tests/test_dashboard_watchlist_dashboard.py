"""Tests for dashboard/watchlist_dashboard.py. Real PostgreSQL throughout."""
import pytest

from dashboard.watchlist_dashboard import WatchlistDashboardService
from watchlist.repository import WatchlistRepository
from watchlist.watchlist_service import WatchlistService

_OWNER_PREFIX = "dash-wl-test-owner"


@pytest.fixture
def repository():
    repo = WatchlistRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM watchlist_items WHERE watchlist_id IN "
                "(SELECT id FROM watchlist_watchlists WHERE owner LIKE %s)", (f"{_OWNER_PREFIX}%",),
            )
            cur.execute("DELETE FROM watchlist_watchlists WHERE owner LIKE %s", (f"{_OWNER_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def watchlist_service(repository):
    return WatchlistService(repository=repository)


@pytest.fixture
def service(watchlist_service):
    return WatchlistDashboardService(watchlist_service)


def _owner(name: str) -> str:
    return f"{_OWNER_PREFIX}-{name}"


def test_build_empty_for_unknown_owner(service):
    view = service.build("nobody@example.com")
    assert view.total_watchlists == 0
    assert view.total_items == 0


def test_build_aggregates_across_watchlists(service, watchlist_service):
    owner = _owner("agg")
    wl1 = watchlist_service.create_watchlist(owner, "Tech")
    wl2 = watchlist_service.create_watchlist(owner, "Crypto")
    watchlist_service.add_symbol(wl1.id, "AAPL", is_favorite=True, folder="Growth")
    watchlist_service.add_symbol(wl1.id, "MSFT", folder="Growth")
    watchlist_service.add_symbol(wl2.id, "BTC-USD", is_favorite=True)
    watchlist_service.add_symbol(wl2.id, "AAPL")

    view = service.build(owner)
    assert view.total_watchlists == 2
    assert view.total_items == 4
    assert view.total_favorites == 2
    assert view.items_by_folder["Growth"] == 2
    assert view.items_by_folder["Unfoldered"] == 2
    assert view.most_tracked_symbols[0] == "AAPL"  # appears twice, across both watchlists


def test_top_n_limits_most_tracked_symbols(service, watchlist_service):
    owner = _owner("topn")
    wl = watchlist_service.create_watchlist(owner, "Big List")
    for symbol in ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA"]:
        watchlist_service.add_symbol(wl.id, symbol)

    view = service.build(owner, top_n=3)
    assert len(view.most_tracked_symbols) == 3
