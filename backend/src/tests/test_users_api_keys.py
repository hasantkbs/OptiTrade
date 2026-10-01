"""Tests for users/api_keys.py. Real PostgreSQL throughout."""
import pytest

from users.api_keys import APIKeyService
from users.audit import AuditService
from users.authentication import AuthenticationService
from users.authorization import AuthorizationService
from users.exceptions import (
    InvalidTokenError,
    MembershipNotFoundError,
    OrganizationNotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
)
from users.models import APIKeyScope, AuditAction, OrganizationQuotas, Role
from users.organizations import OrganizationService
from users.repository import UsersRepository

_EMAIL_PREFIX = "keys-test"


@pytest.fixture
def repo():
    repository = UsersRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        ids = [row[0] for row in cur.fetchall()]
        if ids:
            cur.execute("SELECT id FROM users_organizations WHERE owner_user_id = ANY(%s)", (ids,))
            org_ids = [row[0] for row in cur.fetchall()]
            cur.execute("DELETE FROM users_audit_log WHERE organization_id = ANY(%s) OR actor_user_id = ANY(%s)", (org_ids, ids))
            cur.execute("DELETE FROM users_invitations WHERE organization_id = ANY(%s)", (org_ids,))
            cur.execute(
                "DELETE FROM users_api_key_usage WHERE api_key_id IN "
                "(SELECT id FROM users_api_keys WHERE user_id = ANY(%s))", (ids,),
            )
            cur.execute("DELETE FROM users_api_keys WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_memberships WHERE organization_id = ANY(%s) OR user_id = ANY(%s)", (org_ids, ids))
            cur.execute("DELETE FROM users_organizations WHERE id = ANY(%s)", (org_ids,))
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def auth(repo):
    return AuthenticationService(repo)


@pytest.fixture
def authz(repo):
    return AuthorizationService(repo)


@pytest.fixture
def org_service(repo, authz):
    return OrganizationService(repo, authz)


@pytest.fixture
def audit(repo):
    return AuditService(repo)


@pytest.fixture
def service(repo, authz, audit):
    return APIKeyService(repo, authz, audit)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register(auth, name):
    return auth.register(_email(name), "MyPassw0rd1", name)


def test_create_personal_api_key(service, auth):
    user = _register(auth, "create")
    api_key, raw = service.create_api_key(user.id, "My Key", scope=APIKeyScope.READ_ONLY)
    assert raw.startswith("otk_")
    assert api_key.key_prefix == raw[:12]
    assert api_key.key_hash != raw


def test_create_api_key_rejects_blank_name(service, auth):
    from users.exceptions import ValidationFailedError
    user = _register(auth, "blank")
    with pytest.raises(ValidationFailedError):
        service.create_api_key(user.id, "   ")


def test_authenticate_valid_and_invalid_key(service, auth):
    user = _register(auth, "authvalid")
    _, raw = service.create_api_key(user.id, "Auth Key")
    fetched = service.authenticate(raw)
    assert fetched.user_id == user.id
    with pytest.raises(InvalidTokenError):
        service.authenticate("otk_not-a-real-key")


def test_authenticate_rejects_revoked_key(service, auth):
    user = _register(auth, "revoked")
    api_key, raw = service.create_api_key(user.id, "Revoke Key")
    service.revoke_api_key(user.id, api_key.id)
    with pytest.raises(InvalidTokenError):
        service.authenticate(raw)


def test_authenticate_rejects_expired_key(service, auth):
    user = _register(auth, "expired")
    _, raw = service.create_api_key(user.id, "Expire Key", expires_in_seconds=-10)
    with pytest.raises(InvalidTokenError):
        service.authenticate(raw)


def test_revoke_api_key_requires_ownership(service, auth):
    owner = _register(auth, "revokeown-owner")
    other = _register(auth, "revokeown-other")
    api_key, _ = service.create_api_key(owner.id, "Owned Key")
    with pytest.raises(PermissionDeniedError):
        service.revoke_api_key(other.id, api_key.id)


def test_rotate_api_key_revokes_old_and_creates_new(service, auth):
    user = _register(auth, "rotate")
    old_key, old_raw = service.create_api_key(user.id, "Rotate Key", scope=APIKeyScope.READ_WRITE)
    new_key, new_raw = service.rotate_api_key(user.id, old_key.id)
    assert new_key.rotated_from_id == old_key.id
    assert new_key.scope == APIKeyScope.READ_WRITE
    with pytest.raises(InvalidTokenError):
        service.authenticate(old_raw)
    assert service.authenticate(new_raw).id == new_key.id


def test_rotate_api_key_requires_ownership(service, auth):
    owner = _register(auth, "rotateown-owner")
    other = _register(auth, "rotateown-other")
    api_key, _ = service.create_api_key(owner.id, "Rotate Owned Key")
    with pytest.raises(PermissionDeniedError):
        service.rotate_api_key(other.id, api_key.id)


def test_record_usage_and_stats(service, auth, audit):
    user = _register(auth, "usage")
    api_key, _ = service.create_api_key(user.id, "Usage Key")
    service.record_usage(api_key.id, "/quant/predict", 200)
    service.record_usage(api_key.id, "/quant/predict", 500)
    stats = service.get_usage_stats(api_key.id)
    assert stats.total_requests == 2
    assert stats.error_count == 1
    assert stats.requests_last_24h == 2
    assert stats.last_used_at is not None

    entries = audit.list_for_user(user.id)
    assert any(e.action == AuditAction.API_KEY_USAGE for e in entries)


def test_list_api_keys(service, auth):
    user = _register(auth, "list")
    service.create_api_key(user.id, "List Key 1")
    service.create_api_key(user.id, "List Key 2")
    assert len(service.list_api_keys(user.id)) == 2


def test_org_scoped_key_requires_manage_api_keys_permission(service, org_service, auth):
    owner = _register(auth, "orgperm-owner")
    viewer = _register(auth, "orgperm-viewer")
    org = org_service.create_organization("OrgPermOrg", owner.id)
    _, token = org_service.invite_member(org.id, owner.id, _email("orgperm-viewer"), Role.VIEWER)
    org_service.accept_invitation(token, viewer.id)

    with pytest.raises(PermissionDeniedError):
        service.create_api_key(viewer.id, "Should Fail", organization_id=org.id)


def test_org_scoped_key_enforces_quota(service, org_service, auth):
    owner = _register(auth, "orgquota-owner")
    org = org_service.create_organization("OrgQuotaOrg", owner.id, quotas=OrganizationQuotas(max_api_keys=1))
    service.create_api_key(owner.id, "Key1", organization_id=org.id)
    with pytest.raises(QuotaExceededError):
        service.create_api_key(owner.id, "Key2", organization_id=org.id)


def test_org_scoped_key_raises_for_nonexistent_organization(service, auth):
    user = _register(auth, "nonexistent-org")
    with pytest.raises(OrganizationNotFoundError):
        service.create_api_key(user.id, "Key", organization_id=999999999)


def test_org_scoped_key_raises_for_non_member(service, org_service, auth):
    owner = _register(auth, "nonmember-owner")
    non_member = _register(auth, "nonmember")
    org = org_service.create_organization("NonMemberOrg", owner.id)
    with pytest.raises(MembershipNotFoundError):
        service.create_api_key(non_member.id, "Key", organization_id=org.id)
