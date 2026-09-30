"""Tests for users/organizations.py. Real PostgreSQL throughout."""
import pytest

from users.authentication import AuthenticationService
from users.authorization import AuthorizationService
from users.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidTokenError,
    InvitationNotFoundError,
    LastOwnerError,
    MembershipNotFoundError,
    OrganizationNotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
)
from users.models import OrganizationQuotas, Role
from users.organizations import OrganizationService
from users.repository import UsersRepository

_EMAIL_PREFIX = "orgs-test"


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
                "DELETE FROM users_team_memberships WHERE team_id IN "
                "(SELECT id FROM users_teams WHERE organization_id = ANY(%s))", (org_ids,),
            )
            cur.execute("DELETE FROM users_teams WHERE organization_id = ANY(%s)", (org_ids,))
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
def service(repo, authz):
    return OrganizationService(repo, authz)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register(auth, name):
    return auth.register(_email(name), "MyPassw0rd1", name)


def test_create_organization_makes_creator_owner(service, authz, auth):
    owner = _register(auth, "create-owner")
    org = service.create_organization("Acme", owner.id)
    assert org.name == "Acme"
    assert authz.get_role(owner.id, org.id) == Role.OWNER


def test_create_organization_rejects_blank_name(service, auth):
    owner = _register(auth, "blank-name")
    from users.exceptions import ValidationFailedError
    with pytest.raises(ValidationFailedError):
        service.create_organization("   ", owner.id)


def test_get_organization_raises_for_unknown_id(service):
    with pytest.raises(OrganizationNotFoundError):
        service.get_organization(999999999)


def test_list_organizations_for_user(service, auth):
    owner = _register(auth, "list-owner")
    service.create_organization("Org A", owner.id)
    service.create_organization("Org B", owner.id)
    assert len(service.list_organizations_for_user(owner.id)) == 2


def test_update_organization_requires_manage_organization_permission(service, auth):
    owner = _register(auth, "update-owner")
    outsider = _register(auth, "update-outsider")
    org = service.create_organization("Org", owner.id)

    updated = service.update_organization(org.id, owner.id, name="Renamed")
    assert updated.name == "Renamed"

    with pytest.raises(MembershipNotFoundError):
        service.update_organization(org.id, outsider.id, name="Hacked")


def test_delete_organization(service, auth):
    owner = _register(auth, "delete-owner")
    org = service.create_organization("ToDelete", owner.id)
    service.delete_organization(org.id, owner.id)
    with pytest.raises(OrganizationNotFoundError):
        service.get_organization(org.id)


def test_invite_accept_and_list_members(service, authz, auth):
    owner = _register(auth, "invite-owner")
    invitee = _register(auth, "invite-invitee")
    org = service.create_organization("InviteOrg", owner.id)

    invitation, token = service.invite_member(org.id, owner.id, _email("invite-invitee"), Role.ADMIN)
    assert invitation.email == _email("invite-invitee")
    assert token

    membership = service.accept_invitation(token, invitee.id)
    assert membership.role == Role.ADMIN
    assert authz.get_role(invitee.id, org.id) == Role.ADMIN
    assert len(service.list_members(org.id)) == 2


def test_accept_invitation_rejects_reuse(service, auth):
    owner = _register(auth, "reuse-owner")
    invitee = _register(auth, "reuse-invitee")
    org = service.create_organization("ReuseOrg", owner.id)
    _, token = service.invite_member(org.id, owner.id, _email("reuse-invitee"), Role.VIEWER)
    service.accept_invitation(token, invitee.id)
    with pytest.raises(InvalidTokenError):
        service.accept_invitation(token, invitee.id)


def test_accept_invitation_rejects_wrong_email(service, auth):
    owner = _register(auth, "wrongemail-owner")
    other = _register(auth, "wrongemail-other")
    org = service.create_organization("WrongEmailOrg", owner.id)
    _, token = service.invite_member(org.id, owner.id, _email("someone-else"), Role.VIEWER)
    with pytest.raises(InvalidTokenError):
        service.accept_invitation(token, other.id)


def test_invite_member_rejects_existing_member(service, auth):
    owner = _register(auth, "existing-owner")
    org = service.create_organization("ExistingOrg", owner.id)
    with pytest.raises(EmailAlreadyRegisteredError):
        service.invite_member(org.id, owner.id, _email("existing-owner"), Role.VIEWER)


def test_invite_member_requires_manage_members_permission(service, auth):
    owner = _register(auth, "noperm-owner")
    viewer = _register(auth, "noperm-viewer")
    org = service.create_organization("NoPermOrg", owner.id)
    _, token = service.invite_member(org.id, owner.id, _email("noperm-viewer"), Role.VIEWER)
    service.accept_invitation(token, viewer.id)

    with pytest.raises(PermissionDeniedError):
        service.invite_member(org.id, viewer.id, _email("someone-new"), Role.VIEWER)


def test_invite_member_enforces_member_quota(service, auth):
    owner = _register(auth, "quota-owner")
    org = service.create_organization("QuotaOrg", owner.id, quotas=OrganizationQuotas(max_members=1))
    with pytest.raises(QuotaExceededError):
        service.invite_member(org.id, owner.id, _email("quota-invitee"), Role.VIEWER)


def test_list_and_revoke_invitations(service, auth):
    owner = _register(auth, "revoke-owner")
    org = service.create_organization("RevokeOrg", owner.id)
    invitation, _ = service.invite_member(org.id, owner.id, _email("revoke-invitee"), Role.VIEWER)
    assert len(service.list_invitations(org.id, owner.id)) == 1
    service.revoke_invitation(org.id, owner.id, invitation.id)
    from users.models import InvitationStatus
    invitations = service.list_invitations(org.id, owner.id)
    assert invitations[0].status == InvitationStatus.REVOKED


def test_revoke_invitation_raises_for_unknown_invitation(service, auth):
    owner = _register(auth, "revokeunknown-owner")
    org = service.create_organization("RevokeUnknownOrg", owner.id)
    with pytest.raises(InvitationNotFoundError):
        service.revoke_invitation(org.id, owner.id, 999999999)


def test_change_member_role(service, authz, auth):
    owner = _register(auth, "changerole-owner")
    member = _register(auth, "changerole-member")
    org = service.create_organization("ChangeRoleOrg", owner.id)
    _, token = service.invite_member(org.id, owner.id, _email("changerole-member"), Role.VIEWER)
    service.accept_invitation(token, member.id)

    service.change_member_role(org.id, owner.id, member.id, Role.ANALYST)
    assert authz.get_role(member.id, org.id) == Role.ANALYST


def test_change_member_role_protects_last_owner(service, auth):
    owner = _register(auth, "lastownerrole-owner")
    org = service.create_organization("LastOwnerRoleOrg", owner.id)
    with pytest.raises(LastOwnerError):
        service.change_member_role(org.id, owner.id, owner.id, Role.ADMIN)


def test_remove_member(service, authz, auth):
    owner = _register(auth, "remove-owner")
    member = _register(auth, "remove-member")
    org = service.create_organization("RemoveOrg", owner.id)
    _, token = service.invite_member(org.id, owner.id, _email("remove-member"), Role.VIEWER)
    service.accept_invitation(token, member.id)

    service.remove_member(org.id, owner.id, member.id)
    with pytest.raises(MembershipNotFoundError):
        authz.get_role(member.id, org.id)


def test_remove_member_protects_last_owner(service, auth):
    owner = _register(auth, "lastownerremove-owner")
    org = service.create_organization("LastOwnerRemoveOrg", owner.id)
    with pytest.raises(LastOwnerError):
        service.remove_member(org.id, owner.id, owner.id)


def test_get_resource_usage_without_bridges(service, auth):
    owner = _register(auth, "usage-owner")
    org = service.create_organization("UsageOrg", owner.id)
    usage = service.get_resource_usage(org.id)
    assert usage == {"members": 1, "teams": 0}


def test_get_resource_usage_with_portfolio_and_watchlist_bridges(service, auth):
    owner = _register(auth, "usagebridge-owner")
    org = service.create_organization("UsageBridgeOrg", owner.id)

    class _FakePortfolioService:
        def list_portfolios(self, owner_email):
            return [1, 2] if owner_email == owner.email else []

    class _FakeWatchlistService:
        def list_watchlists(self, owner_email):
            return [1] if owner_email == owner.email else []

    usage = service.get_resource_usage(
        org.id, portfolio_service=_FakePortfolioService(), watchlist_service=_FakeWatchlistService(),
    )
    assert usage["portfolios"] == 2
    assert usage["watchlists"] == 1
