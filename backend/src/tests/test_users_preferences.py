"""Tests for users/preferences.py. Real PostgreSQL throughout, including
real `portfolio`/`watchlist` ownership validation."""
import pytest

from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService
from users.authentication import AuthenticationService
from users.exceptions import PermissionDeniedError, UserNotFoundError, ValidationFailedError
from users.models import Theme
from users.preferences import PreferencesService
from users.repository import UsersRepository
from watchlist.repository import WatchlistRepository
from watchlist.watchlist_service import WatchlistService

_EMAIL_PREFIX = "prefs-test"


@pytest.fixture
def repo():
    repository = UsersRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        ids = [row[0] for row in cur.fetchall()]
        if ids:
            cur.execute("DELETE FROM users_preferences WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def portfolio_repo():
    repository = PortfolioRepository()
    yield repository
    conn = repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM portfolio_portfolios WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))
    finally:
        repository._pool.putconn(conn)


@pytest.fixture
def watchlist_repo():
    repository = WatchlistRepository()
    yield repository
    conn = repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM watchlist_items WHERE watchlist_id IN "
                "(SELECT id FROM watchlist_watchlists WHERE owner LIKE %s)", (f"{_EMAIL_PREFIX}%",),
            )
            cur.execute("DELETE FROM watchlist_watchlists WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))
    finally:
        repository._pool.putconn(conn)


@pytest.fixture
def auth(repo):
    return AuthenticationService(repo)


@pytest.fixture
def portfolio_service(portfolio_repo):
    return PortfolioService(repository=portfolio_repo)


@pytest.fixture
def watchlist_service(watchlist_repo):
    return WatchlistService(repository=watchlist_repo)


@pytest.fixture
def service(repo, portfolio_service, watchlist_service):
    return PreferencesService(repo, portfolio_service=portfolio_service, watchlist_service=watchlist_service)


@pytest.fixture
def bare_service(repo):
    return PreferencesService(repo)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register(auth, name):
    return auth.register(_email(name), "MyPassw0rd1", name)


def test_get_preferences_returns_defaults_for_new_user(bare_service, auth):
    user = _register(auth, "defaults")
    prefs = bare_service.get_preferences(user.id)
    assert prefs.theme == Theme.SYSTEM
    assert prefs.language == "en"
    assert prefs.default_portfolio_id is None


def test_get_preferences_raises_for_unknown_user(bare_service):
    with pytest.raises(UserNotFoundError):
        bare_service.get_preferences(999999999)


def test_update_preferences_persists_simple_fields(bare_service, auth):
    user = _register(auth, "simple")
    updated = bare_service.update_preferences(
        user.id, theme=Theme.DARK, language="tr", notification_settings={"email": False},
        dashboard_layout={"widgets": ["chart"]},
    )
    assert updated.theme == Theme.DARK
    assert updated.language == "tr"
    assert updated.notification_settings == {"email": False}
    assert updated.dashboard_layout == {"widgets": ["chart"]}

    reloaded = bare_service.get_preferences(user.id)
    assert reloaded.theme == Theme.DARK


def test_update_preferences_raises_for_unknown_user(bare_service):
    with pytest.raises(UserNotFoundError):
        bare_service.update_preferences(999999999, theme=Theme.DARK)


def test_default_portfolio_ownership_end_to_end(service, auth, portfolio_service):
    user = _register(auth, "e2e-owner")
    other = _register(auth, "e2e-other")

    my_portfolio = portfolio_service.create_portfolio(user.email, "My Portfolio")
    other_portfolio = portfolio_service.create_portfolio(other.email, "Other Portfolio")

    updated = service.update_preferences(user.id, default_portfolio_id=my_portfolio.id)
    assert updated.default_portfolio_id == my_portfolio.id

    with pytest.raises(PermissionDeniedError):
        service.update_preferences(user.id, default_portfolio_id=other_portfolio.id)

    with pytest.raises(ValidationFailedError):
        service.update_preferences(user.id, default_portfolio_id=999999999)


def test_default_watchlist_ownership_end_to_end(service, auth, watchlist_service):
    user = _register(auth, "wl-owner")
    other = _register(auth, "wl-other")

    my_watchlist = watchlist_service.create_watchlist(user.email, "My Watchlist")
    other_watchlist = watchlist_service.create_watchlist(other.email, "Other Watchlist")

    updated = service.update_preferences(user.id, default_watchlist_id=my_watchlist.id)
    assert updated.default_watchlist_id == my_watchlist.id

    with pytest.raises(PermissionDeniedError):
        service.update_preferences(user.id, default_watchlist_id=other_watchlist.id)

    with pytest.raises(ValidationFailedError):
        service.update_preferences(user.id, default_watchlist_id=999999999)


def test_default_portfolio_skips_validation_without_bridge(bare_service, auth):
    user = _register(auth, "nobridge")
    updated = bare_service.update_preferences(user.id, default_portfolio_id=123456789)
    assert updated.default_portfolio_id == 123456789
