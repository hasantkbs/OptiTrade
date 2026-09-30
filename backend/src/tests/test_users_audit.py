"""Tests for users/audit.py. Real PostgreSQL throughout."""
import pytest

from users.audit import AuditService
from users.authentication import AuthenticationService
from users.models import AuditAction
from users.repository import UsersRepository

_EMAIL_PREFIX = "audit-svc-test"


@pytest.fixture
def repo():
    repository = UsersRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        ids = [row[0] for row in cur.fetchall()]
        if ids:
            cur.execute("DELETE FROM users_audit_log WHERE actor_user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def auth(repo):
    return AuthenticationService(repo)


@pytest.fixture
def service(repo):
    return AuditService(repo)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def test_record_and_list_for_user(service, auth):
    user = auth.register(_email("record"), "MyPassw0rd1", "Record Test")
    service.record(AuditAction.LOGIN, actor_user_id=user.id, target="session", details={"ip": "1.2.3.4"})
    entries = service.list_for_user(user.id)
    assert len(entries) == 1
    assert entries[0].action == AuditAction.LOGIN
    assert entries[0].details == {"ip": "1.2.3.4"}


def test_record_and_list_for_organization(service, auth, repo):
    user = auth.register(_email("org"), "MyPassw0rd1", "Org Test")
    from users.models import Organization
    org_id = repo.save_organization(Organization(name="Audit Org", owner_user_id=user.id))
    service.record(AuditAction.ORGANIZATION_CHANGE, actor_user_id=user.id, organization_id=org_id, target=f"organization:{org_id}")
    entries = service.list_for_organization(org_id)
    assert len(entries) == 1
    assert entries[0].organization_id == org_id

    with repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users_audit_log WHERE organization_id = %s", (org_id,))
        cur.execute("DELETE FROM users_organizations WHERE id = %s", (org_id,))


def test_list_respects_limit(service, auth):
    user = auth.register(_email("limit"), "MyPassw0rd1", "Limit Test")
    for i in range(5):
        service.record(AuditAction.LOGIN, actor_user_id=user.id, target=str(i))
    entries = service.list_for_user(user.id, limit=3)
    assert len(entries) == 3


def test_list_for_user_returns_empty_for_unknown_user(service):
    assert service.list_for_user(999999999) == []
