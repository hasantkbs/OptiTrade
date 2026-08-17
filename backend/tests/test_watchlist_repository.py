"""
Regression tests for watchlist/repository.py's alert pagination
(production audit HIGH #5: "list_alerts() has a fixed LIMIT with no
OFFSET. Once more than 200 enabled alerts exist, newer alerts are never
scanned"). Real PostgreSQL throughout.
"""
import pytest

from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.repository import WatchlistRepository

_OWNER_PREFIX = "wl-repo-test-owner"


@pytest.fixture
def repository():
    repo = WatchlistRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM watchlist_alerts WHERE owner LIKE %s", (f"{_OWNER_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


def _save_alerts(repository, owner, count):
    ids = []
    for i in range(count):
        alert = Alert(
            owner=owner, symbol=f"SYM{i}", category=AlertCategory.PRICE, alert_type=AlertType.PRICE_ABOVE,
            parameters={"threshold": 1.0},
        )
        ids.append(repository.save_alert(alert))
    return ids


def test_list_alerts_pages_through_more_than_one_batch(repository):
    owner = f"{_OWNER_PREFIX}-paging"
    created_ids = _save_alerts(repository, owner, 12)

    page1 = repository.list_alerts(owner=owner, enabled_only=True, limit=5, offset=0)
    page2 = repository.list_alerts(owner=owner, enabled_only=True, limit=5, offset=5)
    page3 = repository.list_alerts(owner=owner, enabled_only=True, limit=5, offset=10)

    assert [a.id for a in page1] == created_ids[0:5]
    assert [a.id for a in page2] == created_ids[5:10]
    assert [a.id for a in page3] == created_ids[10:12]
    assert len(page3) == 2  # last page is short - the "reached the end" signal callers rely on


def test_list_alerts_pages_never_overlap_or_skip(repository):
    owner = f"{_OWNER_PREFIX}-no-gaps"
    created_ids = set(_save_alerts(repository, owner, 23))

    seen = []
    offset = 0
    while True:
        page = repository.list_alerts(owner=owner, enabled_only=True, limit=7, offset=offset)
        if not page:
            break
        seen.extend(a.id for a in page)
        offset += len(page)

    assert len(seen) == len(set(seen))  # no duplicates across pages
    assert set(seen) == created_ids  # every alert covered exactly once


def test_count_alerts_matches_the_number_saved(repository):
    owner = f"{_OWNER_PREFIX}-count"
    _save_alerts(repository, owner, 9)
    assert repository.count_alerts(owner=owner, enabled_only=True) == 9


def test_count_alerts_excludes_disabled_when_enabled_only(repository):
    owner = f"{_OWNER_PREFIX}-count-disabled"
    ids = _save_alerts(repository, owner, 5)
    repository.set_alert_enabled(ids[0], False)
    assert repository.count_alerts(owner=owner, enabled_only=True) == 4
    assert repository.count_alerts(owner=owner, enabled_only=False) == 5
