"""Tests for users/teams.py. Real PostgreSQL throughout."""
import pytest

from users.authentication import AuthenticationService
from users.authorization import AuthorizationService
from users.exceptions import MembershipNotFoundError, PermissionDeniedError, QuotaExceededError, TeamNotFoundError
from users.models import OrganizationQuotas, Role
from users.organizations import OrganizationService
from users.repository import UsersRepository
from users.teams import TeamService

_EMAIL_PREFIX = "teams-test"


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
def org_service(repo, authz):
    return OrganizationService(repo, authz)


@pytest.fixture
def service(repo, authz):
    return TeamService(repo, authz)


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register(auth, name):
    return auth.register(_email(name), "MyPassw0rd1", name)


def test_create_and_get_team(service, org_service, auth):
    owner = _register(auth, "create-owner")
    org = org_service.create_organization("Org", owner.id)
    team = service.create_team(org.id, owner.id, "Core Team")
    assert team.name == "Core Team"
    assert service.get_team(team.id).id == team.id


def test_get_team_raises_for_unknown_id(service):
    with pytest.raises(TeamNotFoundError):
        service.get_team(999999999)


def test_create_team_requires_manage_teams_permission(service, org_service, auth):
    owner = _register(auth, "perm-owner")
    viewer = _register(auth, "perm-viewer")
    org = org_service.create_organization("PermOrg", owner.id)
    _, token = org_service.invite_member(org.id, owner.id, _email("perm-viewer"), Role.VIEWER)
    org_service.accept_invitation(token, viewer.id)

    with pytest.raises(PermissionDeniedError):
        service.create_team(org.id, viewer.id, "Should Fail")


def test_create_team_enforces_quota(service, org_service, auth):
    owner = _register(auth, "quota-owner")
    org = org_service.create_organization("QuotaOrg", owner.id, quotas=OrganizationQuotas(max_teams=1))
    service.create_team(org.id, owner.id, "Team 1")
    with pytest.raises(QuotaExceededError):
        service.create_team(org.id, owner.id, "Team 2")


def test_list_teams(service, org_service, auth):
    owner = _register(auth, "list-owner")
    org = org_service.create_organization("ListOrg", owner.id, quotas=OrganizationQuotas(max_teams=5))
    service.create_team(org.id, owner.id, "Team A")
    service.create_team(org.id, owner.id, "Team B")
    assert len(service.list_teams(org.id)) == 2


def test_delete_team(service, org_service, auth):
    owner = _register(auth, "delete-owner")
    org = org_service.create_organization("DeleteOrg", owner.id)
    team = service.create_team(org.id, owner.id, "ToDelete")
    service.delete_team(org.id, owner.id, team.id)
    with pytest.raises(TeamNotFoundError):
        service.get_team(team.id)


def test_delete_team_raises_for_team_in_different_organization(service, org_service, auth):
    owner = _register(auth, "wrongorg-owner")
    org1 = org_service.create_organization("Org1", owner.id, quotas=OrganizationQuotas(max_teams=5))
    org2 = org_service.create_organization("Org2", owner.id, quotas=OrganizationQuotas(max_teams=5))
    team = service.create_team(org1.id, owner.id, "Team")
    with pytest.raises(TeamNotFoundError):
        service.delete_team(org2.id, owner.id, team.id)


def test_add_and_remove_team_member(service, org_service, auth):
    owner = _register(auth, "addmember-owner")
    member = _register(auth, "addmember-member")
    org = org_service.create_organization("AddMemberOrg", owner.id)
    _, token = org_service.invite_member(org.id, owner.id, _email("addmember-member"), Role.VIEWER)
    org_service.accept_invitation(token, member.id)
    team = service.create_team(org.id, owner.id, "Team")

    service.add_member(org.id, owner.id, team.id, member.id)
    assert len(service.list_members(team.id)) == 1

    service.remove_member(org.id, owner.id, team.id, member.id)
    assert service.list_members(team.id) == []


def test_add_member_rejects_non_org_member(service, org_service, auth):
    owner = _register(auth, "nonmember-owner")
    outsider = _register(auth, "nonmember-outsider")
    org = org_service.create_organization("NonMemberOrg", owner.id)
    team = service.create_team(org.id, owner.id, "Team")
    with pytest.raises(MembershipNotFoundError):
        service.add_member(org.id, owner.id, team.id, outsider.id)
