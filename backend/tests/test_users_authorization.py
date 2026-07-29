"""Tests for users/authorization.py. Real PostgreSQL throughout."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from users.authentication import AuthenticationService, create_access_token
from users.authorization import (
    ROLE_PERMISSIONS,
    AuthorizationService,
    get_current_user,
    has_permission,
    require_permission,
)
from users.exceptions import MembershipNotFoundError, PermissionDeniedError
from users.models import Membership, Organization, Permission, Role, User
from users.repository import UsersRepository

_EMAIL_PREFIX = "authz-test"


@pytest.fixture
def repo():
    repository = UsersRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        ids = [row[0] for row in cur.fetchall()]
        if ids:
            cur.execute("DELETE FROM users_memberships WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_organizations WHERE owner_user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def auth_service(repo):
    return AuthenticationService(repo)


@pytest.fixture
def authz(repo):
    return AuthorizationService(repo)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


# ── ROLE_PERMISSIONS mapping ─────────────────────────────────────────────

def test_owner_has_every_permission():
    assert ROLE_PERMISSIONS[Role.OWNER] == frozenset(Permission)


def test_viewer_only_has_view_permissions():
    for permission in ROLE_PERMISSIONS[Role.VIEWER]:
        assert permission.value.startswith("view_")


def test_has_permission_owner_true_viewer_false():
    assert has_permission(Role.OWNER, Permission.MANAGE_ORGANIZATION)
    assert not has_permission(Role.VIEWER, Permission.MANAGE_ORGANIZATION)


def test_admin_cannot_manage_organization_but_can_manage_members():
    assert not has_permission(Role.ADMIN, Permission.MANAGE_ORGANIZATION)
    assert has_permission(Role.ADMIN, Permission.MANAGE_MEMBERS)


def test_analyst_cannot_manage_portfolios():
    assert not has_permission(Role.ANALYST, Permission.MANAGE_PORTFOLIOS)
    assert has_permission(Role.ANALYST, Permission.VIEW_PORTFOLIOS)


# ── AuthorizationService ─────────────────────────────────────────────────

def test_get_role_returns_membership_role(repo, authz):
    user_id = repo.save_user(User(email=_email("role"), password_hash="h", display_name="Role Test"))
    org_id = repo.save_organization(Organization(name="Org", owner_user_id=user_id))
    repo.save_membership(Membership(user_id=user_id, organization_id=org_id, role=Role.ADMIN))
    assert authz.get_role(user_id, org_id) == Role.ADMIN


def test_get_role_raises_for_non_member(authz):
    with pytest.raises(MembershipNotFoundError):
        authz.get_role(999999999, 999999999)


def test_check_permission_raises_for_insufficient_role(repo, authz):
    user_id = repo.save_user(User(email=_email("perm"), password_hash="h", display_name="Perm Test"))
    org_id = repo.save_organization(Organization(name="Org2", owner_user_id=user_id))
    repo.save_membership(Membership(user_id=user_id, organization_id=org_id, role=Role.VIEWER))
    with pytest.raises(PermissionDeniedError):
        authz.check_permission(user_id, org_id, Permission.MANAGE_PORTFOLIOS)


def test_check_permission_passes_for_sufficient_role(repo, authz):
    user_id = repo.save_user(User(email=_email("perm2"), password_hash="h", display_name="Perm Test 2"))
    org_id = repo.save_organization(Organization(name="Org3", owner_user_id=user_id))
    repo.save_membership(Membership(user_id=user_id, organization_id=org_id, role=Role.OWNER))
    authz.check_permission(user_id, org_id, Permission.MANAGE_PORTFOLIOS)  # must not raise


def test_is_last_owner(repo, authz):
    owner_id = repo.save_user(User(email=_email("lastowner"), password_hash="h", display_name="Last Owner"))
    other_id = repo.save_user(User(email=_email("otherowner"), password_hash="h", display_name="Other"))
    org_id = repo.save_organization(Organization(name="Org4", owner_user_id=owner_id))
    repo.save_membership(Membership(user_id=owner_id, organization_id=org_id, role=Role.OWNER))
    assert authz.is_last_owner(owner_id, org_id) is True

    repo.save_membership(Membership(user_id=other_id, organization_id=org_id, role=Role.OWNER))
    assert authz.is_last_owner(owner_id, org_id) is False


# ── FastAPI dependencies ─────────────────────────────────────────────────

@pytest.fixture
def app(repo):
    application = FastAPI()
    current_user_dep = get_current_user(repo)
    require_manage_portfolios = require_permission(Permission.MANAGE_PORTFOLIOS, repo, current_user_dep)

    @application.get("/whoami")
    def whoami(user=Depends(current_user_dep)):
        return {"user_id": user.id}

    @application.get("/orgs/{organization_id}/protected")
    def protected(organization_id: int, user=Depends(require_manage_portfolios)):
        return {"ok": True}

    return application


def test_get_current_user_dependency_requires_bearer_token(app):
    client = TestClient(app)
    assert client.get("/whoami").status_code == 401


def test_get_current_user_dependency_rejects_garbage_token(app):
    client = TestClient(app)
    r = client.get("/whoami", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_get_current_user_dependency_accepts_valid_token(app, repo, auth_service):
    user = auth_service.register(_email("dep"), "MyPassw0rd1", "Dep Test")
    token = create_access_token(user.id)
    client = TestClient(app)
    r = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["user_id"] == user.id


def test_require_permission_dependency_grants_and_denies(app, repo, auth_service):
    user = auth_service.register(_email("reqperm"), "MyPassw0rd1", "Req Perm")
    org_id = repo.save_organization(Organization(name="ReqPermOrg", owner_user_id=user.id))
    repo.save_membership(Membership(user_id=user.id, organization_id=org_id, role=Role.OWNER))
    token = create_access_token(user.id)
    client = TestClient(app)

    r = client.get(f"/orgs/{org_id}/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    repo.save_membership(Membership(user_id=user.id, organization_id=org_id, role=Role.VIEWER))
    r = client.get(f"/orgs/{org_id}/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
