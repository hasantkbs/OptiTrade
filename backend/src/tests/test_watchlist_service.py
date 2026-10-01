"""Tests for watchlist/watchlist_service.py. Real PostgreSQL throughout."""
import pytest

from watchlist.exceptions import WatchlistItemNotFoundError, WatchlistNotFoundError
from watchlist.repository import WatchlistRepository
from watchlist.watchlist_service import WatchlistService

_OWNER_PREFIX = "wl-svc-test-owner"


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
def service(repository):
    return WatchlistService(repository=repository)


def _owner(name: str) -> str:
    return f"{_OWNER_PREFIX}-{name}"


def test_create_and_get_watchlist(service):
    watchlist = service.create_watchlist(_owner("create"), "Main")
    assert watchlist.id is not None
    fetched = service.get_watchlist(watchlist.id)
    assert fetched.name == "Main"


def test_get_watchlist_raises_for_unknown_id(service):
    with pytest.raises(WatchlistNotFoundError):
        service.get_watchlist(999999999)


def test_unlimited_watchlists_per_owner(service):
    owner = _owner("unlimited")
    for i in range(5):
        service.create_watchlist(owner, f"List {i}")
    assert len(service.list_watchlists(owner)) == 5


def test_list_watchlists_scoped_to_owner(service):
    service.create_watchlist(_owner("scope-a"), "A")
    service.create_watchlist(_owner("scope-b"), "B")
    assert len(service.list_watchlists(_owner("scope-a"))) == 1


def test_delete_watchlist_removes_it_and_its_items(service):
    watchlist = service.create_watchlist(_owner("delete"), "ToDelete")
    service.add_symbol(watchlist.id, "AAPL")
    service.delete_watchlist(watchlist.id)
    with pytest.raises(WatchlistNotFoundError):
        service.get_watchlist(watchlist.id)


def test_add_symbol_with_favorite_folder_tags_notes(service):
    watchlist = service.create_watchlist(_owner("items"), "Items")
    item = service.add_symbol(
        watchlist.id, "aapl", is_favorite=True, folder="Tech", tags=["growth", "ai"], notes="watch closely",
    )
    assert item.symbol == "AAPL"
    assert item.is_favorite is True
    assert item.folder == "Tech"
    assert item.tags == ["growth", "ai"]
    assert item.notes == "watch closely"


def test_add_symbol_twice_updates_rather_than_duplicates(service):
    watchlist = service.create_watchlist(_owner("upsert"), "Upsert")
    service.add_symbol(watchlist.id, "AAPL", folder="A")
    service.add_symbol(watchlist.id, "AAPL", folder="B")
    items = service.list_items(watchlist.id)
    assert len(items) == 1
    assert items[0].folder == "B"


def test_remove_symbol(service):
    watchlist = service.create_watchlist(_owner("remove"), "Remove")
    service.add_symbol(watchlist.id, "AAPL")
    service.remove_symbol(watchlist.id, "AAPL")
    assert service.list_items(watchlist.id) == []


def test_get_item_raises_for_symbol_not_in_watchlist(service):
    watchlist = service.create_watchlist(_owner("missing-item"), "Missing")
    with pytest.raises(WatchlistItemNotFoundError):
        service.get_item(watchlist.id, "AAPL")


def test_list_favorites_folder_and_tag(service):
    watchlist = service.create_watchlist(_owner("filters"), "Filters")
    service.add_symbol(watchlist.id, "AAPL", is_favorite=True, folder="Tech", tags=["ai"])
    service.add_symbol(watchlist.id, "MSFT", folder="Tech", tags=["ai", "cloud"])
    service.add_symbol(watchlist.id, "GARAN.IS", folder="BIST", tags=["bank"])

    assert {item.symbol for item in service.list_favorites(watchlist.id)} == {"AAPL"}
    assert {item.symbol for item in service.list_by_folder(watchlist.id, "Tech")} == {"AAPL", "MSFT"}
    assert {item.symbol for item in service.list_by_tag(watchlist.id, "ai")} == {"AAPL", "MSFT"}


def test_set_favorite_folder_tags_notes(service):
    watchlist = service.create_watchlist(_owner("mutate"), "Mutate")
    service.add_symbol(watchlist.id, "AAPL")

    service.set_favorite(watchlist.id, "AAPL", True)
    assert service.get_item(watchlist.id, "AAPL").is_favorite is True

    service.set_folder(watchlist.id, "AAPL", "Growth")
    assert service.get_item(watchlist.id, "AAPL").folder == "Growth"

    service.set_tags(watchlist.id, "AAPL", ["a", "b"])
    assert service.get_item(watchlist.id, "AAPL").tags == ["a", "b"]

    service.set_notes(watchlist.id, "AAPL", "long term hold")
    assert service.get_item(watchlist.id, "AAPL").notes == "long term hold"


def test_service_defaults_to_real_dependencies():
    service = WatchlistService()
    assert isinstance(service.repository, WatchlistRepository)
