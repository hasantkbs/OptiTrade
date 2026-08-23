"""Tests for users/repository.py. Real PostgreSQL throughout."""
from datetime import datetime, timedelta, timezone

import pytest

from users.models import (
    APIKey,
    APIKeyScope,
    APIKeyUsageRecord,
    AuditAction,
    AuditLogEntry,
    DeviceInfo,
    Invitation,
    InvitationStatus,
    LoginHistoryEntry,
    Membership,
    Organization,
    PasswordResetToken,
    Role,
    Session,
    Team,
    TeamMembership,
    User,
    UserPreferences,
)
from users.repository import UsersRepository

_EMAIL_PREFIX = "repo-test"


@pytest.fixture
def repo():
    repository = UsersRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(f"SELECT id FROM users_users WHERE email LIKE '{_EMAIL_PREFIX}%'")
        ids = [row[0] for row in cur.fetchall()]
        if ids:
            cur.execute("DELETE FROM users_audit_log WHERE actor_user_id = ANY(%s)", (ids,))
            cur.execute(
                "DELETE FROM users_api_key_usage WHERE api_key_id IN "
                "(SELECT id FROM users_api_keys WHERE user_id = ANY(%s))", (ids,),
            )
            cur.execute("DELETE FROM users_api_keys WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_preferences WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_password_reset_tokens WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_invitations WHERE invited_by = ANY(%s)", (ids,))
            cur.execute(
                "DELETE FROM users_team_memberships WHERE team_id IN "
                "(SELECT id FROM users_teams WHERE organization_id IN "
                "(SELECT id FROM users_organizations WHERE owner_user_id = ANY(%s)))", (ids,),
            )
            cur.execute(
                "DELETE FROM users_teams WHERE organization_id IN "
                "(SELECT id FROM users_organizations WHERE owner_user_id = ANY(%s))", (ids,),
            )
            cur.execute("DELETE FROM users_memberships WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_organizations WHERE owner_user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _make_user(name: str) -> User:
    return User(email=_email(name), password_hash="hash", display_name=f"Test {name}")


def test_save_and_get_user(repo):
    user_id = repo.save_user(_make_user("get"))
    fetched = repo.get_user(user_id)
    assert fetched.email == _email("get")
    assert fetched.display_name == "Test get"


def test_email_is_lowercased(repo):
    user = User(email=_email("CASE").upper(), password_hash="h", display_name="Case")
    user_id = repo.save_user(user)
    assert repo.get_user(user_id).email == _email("case")


def test_get_user_by_email(repo):
    repo.save_user(_make_user("byemail"))
    fetched = repo.get_user_by_email(_email("byemail").upper())
    assert fetched is not None
    assert fetched.email == _email("byemail")


def test_get_user_returns_none_for_unknown_id(repo):
    assert repo.get_user(999999999) is None


def test_update_user(repo):
    user_id = repo.save_user(_make_user("update"))
    user = repo.get_user(user_id)
    user.display_name = "Updated Name"
    user.is_active = False
    repo.update_user(user)
    assert repo.get_user(user_id).display_name == "Updated Name"
    assert repo.get_user(user_id).is_active is False


def test_save_and_get_organization(repo):
    owner_id = repo.save_user(_make_user("org-owner"))
    org_id = repo.save_organization(Organization(name="Test Org", owner_user_id=owner_id))
    org = repo.get_organization(org_id)
    assert org.name == "Test Org"
    assert org.quotas.max_members == 10


def test_list_organizations_for_user(repo):
    owner_id = repo.save_user(_make_user("org-list-owner"))
    org_id = repo.save_organization(Organization(name="Org A", owner_user_id=owner_id))
    repo.save_membership(Membership(user_id=owner_id, organization_id=org_id, role=Role.OWNER))
    orgs = repo.list_organizations_for_user(owner_id)
    assert len(orgs) == 1
    assert orgs[0].id == org_id


def test_update_organization(repo):
    owner_id = repo.save_user(_make_user("org-update-owner"))
    org_id = repo.save_organization(Organization(name="Old Name", owner_user_id=owner_id))
    org = repo.get_organization(org_id)
    org.name = "New Name"
    repo.update_organization(org)
    assert repo.get_organization(org_id).name == "New Name"


def test_delete_organization_cascades(repo):
    owner_id = repo.save_user(_make_user("org-delete-owner"))
    org_id = repo.save_organization(Organization(name="ToDelete", owner_user_id=owner_id))
    team_id = repo.save_team(Team(organization_id=org_id, name="Team"))
    repo.add_team_member(TeamMembership(team_id=team_id, user_id=owner_id))
    repo.save_membership(Membership(user_id=owner_id, organization_id=org_id, role=Role.OWNER))
    repo.delete_organization(org_id)
    assert repo.get_organization(org_id) is None
    assert repo.list_teams(org_id) == []


def test_save_and_get_team(repo):
    owner_id = repo.save_user(_make_user("team-owner"))
    org_id = repo.save_organization(Organization(name="Team Org", owner_user_id=owner_id))
    team_id = repo.save_team(Team(organization_id=org_id, name="Core"))
    team = repo.get_team(team_id)
    assert team.name == "Core"
    assert len(repo.list_teams(org_id)) == 1


def test_delete_team(repo):
    owner_id = repo.save_user(_make_user("team-delete-owner"))
    org_id = repo.save_organization(Organization(name="Team Org 2", owner_user_id=owner_id))
    team_id = repo.save_team(Team(organization_id=org_id, name="Core"))
    repo.delete_team(team_id)
    assert repo.get_team(team_id) is None


def test_team_membership_add_remove_list(repo):
    owner_id = repo.save_user(_make_user("team-member-owner"))
    org_id = repo.save_organization(Organization(name="TM Org", owner_user_id=owner_id))
    team_id = repo.save_team(Team(organization_id=org_id, name="TM Team"))
    repo.add_team_member(TeamMembership(team_id=team_id, user_id=owner_id))
    assert len(repo.list_team_members(team_id)) == 1
    repo.remove_team_member(team_id, owner_id)
    assert repo.list_team_members(team_id) == []


def test_membership_save_get_list_delete(repo):
    user_id = repo.save_user(_make_user("membership-user"))
    org_id = repo.save_organization(Organization(name="M Org", owner_user_id=user_id))
    repo.save_membership(Membership(user_id=user_id, organization_id=org_id, role=Role.VIEWER))
    membership = repo.get_membership(user_id, org_id)
    assert membership.role == Role.VIEWER
    assert len(repo.list_memberships(org_id)) == 1

    membership.role = Role.ADMIN
    repo.save_membership(membership)
    assert repo.get_membership(user_id, org_id).role == Role.ADMIN

    repo.delete_membership(user_id, org_id)
    assert repo.get_membership(user_id, org_id) is None


def test_invitation_lifecycle(repo):
    owner_id = repo.save_user(_make_user("inv-owner"))
    org_id = repo.save_organization(Organization(name="Inv Org", owner_user_id=owner_id))
    invitation_id = repo.save_invitation(
        Invitation(
            organization_id=org_id, email=_email("invitee"), role=Role.VIEWER, invited_by=owner_id,
            token_hash="tokhash1", expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    invitation = repo.get_invitation(invitation_id)
    assert invitation.email == _email("invitee")
    assert repo.get_invitation_by_token_hash("tokhash1").id == invitation_id
    assert len(repo.list_invitations(org_id)) == 1

    repo.update_invitation_status(invitation_id, InvitationStatus.ACCEPTED)
    assert repo.get_invitation(invitation_id).status == InvitationStatus.ACCEPTED


def test_session_lifecycle(repo):
    user_id = repo.save_user(_make_user("session-user"))
    session_id = repo.save_session(
        Session(
            user_id=user_id, refresh_token_hash="rtokhash", device=DeviceInfo(user_agent="ua", ip_address="1.2.3.4"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    session = repo.get_session(session_id)
    assert session.device.user_agent == "ua"
    assert repo.get_session_by_token_hash("rtokhash").id == session_id
    assert len(repo.list_sessions(user_id)) == 1

    session.revoked_at = datetime.now(timezone.utc)
    repo.update_session(session)
    assert repo.get_session(session_id).revoked_at is not None


def test_login_history(repo):
    user_id = repo.save_user(_make_user("history-user"))
    repo.save_login_history(
        LoginHistoryEntry(user_id=user_id, email=_email("history-user"), success=True, device=DeviceInfo(user_agent="ua"))
    )
    history = repo.list_login_history(user_id)
    assert len(history) == 1
    assert history[0].success is True


def test_password_reset_token_lifecycle(repo):
    user_id = repo.save_user(_make_user("reset-user"))
    token_id = repo.save_password_reset_token(
        PasswordResetToken(user_id=user_id, token_hash="resethash", expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    )
    token = repo.get_password_reset_token_by_hash("resethash")
    assert token.id == token_id
    repo.mark_password_reset_token_used(token_id, datetime.now(timezone.utc))
    assert repo.get_password_reset_token_by_hash("resethash").used_at is not None


def test_api_key_lifecycle(repo):
    user_id = repo.save_user(_make_user("key-user"))
    api_key_id = repo.save_api_key(
        APIKey(user_id=user_id, name="Key1", key_prefix="otk_abcd", key_hash="keyhash1", scope=APIKeyScope.READ_ONLY)
    )
    key = repo.get_api_key(api_key_id)
    assert key.name == "Key1"
    assert repo.get_api_key_by_hash("keyhash1").id == api_key_id
    assert len(repo.list_api_keys(user_id)) == 1

    key.revoked_at = datetime.now(timezone.utc)
    repo.update_api_key(key)
    assert repo.get_api_key(api_key_id).revoked_at is not None


def test_api_key_usage(repo):
    user_id = repo.save_user(_make_user("usage-user"))
    api_key_id = repo.save_api_key(
        APIKey(user_id=user_id, name="UsageKey", key_prefix="otk_efgh", key_hash="keyhash2")
    )
    repo.save_api_key_usage(APIKeyUsageRecord(api_key_id=api_key_id, endpoint="/foo", status_code=200))
    records = repo.list_api_key_usage(api_key_id)
    assert len(records) == 1
    assert records[0].status_code == 200


def test_preferences_upsert(repo):
    user_id = repo.save_user(_make_user("prefs-user"))
    repo.save_preferences(UserPreferences(user_id=user_id, default_portfolio_id=5))
    prefs = repo.get_preferences(user_id)
    assert prefs.default_portfolio_id == 5

    prefs.language = "tr"
    repo.save_preferences(prefs)
    assert repo.get_preferences(user_id).language == "tr"


def test_audit_log_record_and_query(repo):
    user_id = repo.save_user(_make_user("audit-user"))
    org_id = repo.save_organization(Organization(name="Audit Org", owner_user_id=user_id))
    repo.save_audit_entry(
        AuditLogEntry(actor_user_id=user_id, organization_id=org_id, action=AuditAction.LOGIN, details={"ip": "1.2.3.4"})
    )
    by_org = repo.list_audit_log(organization_id=org_id)
    assert len(by_org) == 1
    by_user = repo.list_audit_log(actor_user_id=user_id)
    assert len(by_user) == 1


def test_purge_old_audit_history_deletes_rows_past_retention(repo):
    user_id = repo.save_user(_make_user("purge-old"))
    org_id = repo.save_organization(Organization(name="Purge Org", owner_user_id=user_id))
    old = datetime.now(timezone.utc) - timedelta(days=400)
    repo.save_login_history(LoginHistoryEntry(user_id=user_id, email=_email("purge-old"), success=True, occurred_at=old))
    repo.save_audit_entry(
        AuditLogEntry(actor_user_id=user_id, organization_id=org_id, action=AuditAction.LOGIN, occurred_at=old)
    )
    api_key_id = repo.save_api_key(
        APIKey(user_id=user_id, name="PurgeKey", key_prefix="otk_purg", key_hash="purgehash")
    )
    repo.save_api_key_usage(APIKeyUsageRecord(api_key_id=api_key_id, endpoint="/foo", status_code=200, occurred_at=old))

    deleted = repo.purge_old_audit_history(retention_days=365)

    assert deleted["users_login_history"] == 1
    assert deleted["users_audit_log"] == 1
    assert deleted["users_api_key_usage"] == 1
    assert repo.list_login_history(user_id) == []
    assert repo.list_audit_log(actor_user_id=user_id) == []
    assert repo.list_api_key_usage(api_key_id) == []


def test_purge_old_audit_history_keeps_rows_within_retention(repo):
    user_id = repo.save_user(_make_user("purge-recent"))
    recent = datetime.now(timezone.utc) - timedelta(days=10)
    repo.save_login_history(
        LoginHistoryEntry(user_id=user_id, email=_email("purge-recent"), success=True, occurred_at=recent)
    )

    deleted = repo.purge_old_audit_history(retention_days=365)

    assert deleted["users_login_history"] == 0
    assert len(repo.list_login_history(user_id)) == 1


def test_purge_old_audit_history_uses_configured_default_when_no_argument_given(repo, monkeypatch):
    import users.repository as repository_module

    monkeypatch.setattr(repository_module, "_DEFAULT_AUDIT_HISTORY_RETENTION_DAYS", 30)
    user_id = repo.save_user(_make_user("purge-default"))
    old = datetime.now(timezone.utc) - timedelta(days=40)
    repo.save_login_history(
        LoginHistoryEntry(user_id=user_id, email=_email("purge-default"), success=True, occurred_at=old)
    )

    deleted = repo.purge_old_audit_history()

    assert deleted["users_login_history"] == 1


def test_ping(repo):
    assert repo.ping() is True
