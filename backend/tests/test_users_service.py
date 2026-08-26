"""Tests for users/service.py. Real PostgreSQL throughout."""
import pytest

from users.exceptions import EmailAlreadyRegisteredError, UserNotFoundError
from users.repository import UsersRepository
from users.service import UserService

_EMAIL_PREFIX = "svc-test"


@pytest.fixture
def repo():
    repository = UsersRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        ids = [row[0] for row in cur.fetchall()]
        if ids:
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def service(repo):
    return UserService(repo)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def test_register(service):
    user = service.register(_email("register"), "MyPassw0rd1", "Register Test")
    assert user.id is not None
    assert user.email == _email("register")


def test_register_rejects_duplicate(service):
    service.register(_email("dup"), "MyPassw0rd1", "Dup")
    with pytest.raises(EmailAlreadyRegisteredError):
        service.register(_email("dup"), "AnotherPass1", "Dup Again")


def test_get_by_id_and_email(service):
    user = service.register(_email("get"), "MyPassw0rd1", "Get Test")
    assert service.get_by_id(user.id).email == _email("get")
    assert service.get_by_email(_email("get")).id == user.id


def test_get_by_id_raises_for_unknown_user(service):
    with pytest.raises(UserNotFoundError):
        service.get_by_id(999999999)


def test_get_by_email_raises_for_unknown_email(service):
    with pytest.raises(UserNotFoundError):
        service.get_by_email("nobody@example.com")


def test_update_profile(service):
    user = service.register(_email("update"), "MyPassw0rd1", "Update Test")
    updated = service.update_profile(user.id, display_name="New Name")
    assert updated.display_name == "New Name"


def test_update_profile_rejects_blank_name(service):
    from users.exceptions import ValidationFailedError
    user = service.register(_email("blank"), "MyPassw0rd1", "Blank Test")
    with pytest.raises(ValidationFailedError):
        service.update_profile(user.id, display_name="   ")


def test_deactivate_and_reactivate(service):
    user = service.register(_email("deactivate"), "MyPassw0rd1", "Deactivate Test")
    deactivated = service.deactivate(user.id)
    assert deactivated.is_active is False
    reactivated = service.reactivate(user.id)
    assert reactivated.is_active is True
