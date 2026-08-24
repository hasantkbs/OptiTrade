"""Integration tests for the User & Organization Platform endpoints
wired into main.py. Uses the shared `client` fixture (real main.app,
real startup, self-evolution loop stubbed out - see conftest.py). Real
PostgreSQL/Redis throughout."""
import pytest

from users.repository import UsersRepository

_EMAIL_PREFIX = "main-users-test"


@pytest.fixture
def cleanup():
    yield
    repo = UsersRepository()
    with repo._connection() as conn, conn, conn.cursor() as cur:
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
            cur.execute(
                "DELETE FROM users_api_key_usage WHERE api_key_id IN "
                "(SELECT id FROM users_api_keys WHERE user_id = ANY(%s))", (ids,),
            )
            cur.execute("DELETE FROM users_api_keys WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_preferences WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_password_reset_tokens WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_login_history WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_sessions WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users_users WHERE id = ANY(%s)", (ids,))
    repo.close()


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _register_and_login(client, name):
    client.post("/auth/register", json={"email": _email(name), "password": "MyPassw0rd1", "display_name": name})
    r = client.post("/auth/login", json={"email": _email(name), "password": "MyPassw0rd1"})
    tokens = r.json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


def test_register_login_and_get_me(client, cleanup):
    r = client.post("/auth/register", json={"email": _email("basic"), "password": "MyPassw0rd1", "display_name": "Basic"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == _email("basic")

    r = client.post("/auth/login", json={"email": _email("basic"), "password": "MyPassw0rd1"})
    assert r.status_code == 200, r.text
    tokens = r.json()

    r = client.get("/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200
    assert r.json()["email"] == _email("basic")


def test_register_rejects_duplicate_email(client, cleanup):
    client.post("/auth/register", json={"email": _email("dup"), "password": "MyPassw0rd1", "display_name": "Dup"})
    r = client.post("/auth/register", json={"email": _email("dup"), "password": "MyPassw0rd1", "display_name": "Dup2"})
    assert r.status_code == 400


def test_login_wrong_password_returns_401(client, cleanup):
    client.post("/auth/register", json={"email": _email("wrongpw"), "password": "MyPassw0rd1", "display_name": "WP"})
    r = client.post("/auth/login", json={"email": _email("wrongpw"), "password": "WrongPassword1"})
    assert r.status_code == 401


def test_me_requires_authentication(client, cleanup):
    assert client.get("/users/me").status_code == 401
    assert client.get("/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_me_rejects_a_malformed_token_without_leaking_the_underlying_library_error(client, cleanup):
    """E2E regression (API contract audit): a token with dot-separated
    segments but undecodable base64 content used to surface jose's raw
    "'utf-8' codec can't decode byte ..." exception text verbatim in the
    401 response body - an internal-implementation leak. Every invalid-
    token case must return the same clean, generic message."""
    r = client.get("/users/me", headers={"Authorization": "Bearer garbage.not.a.jwt"})
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail == "invalid or expired access token"
    assert "codec" not in detail
    assert "utf-8" not in detail.lower()


def test_refresh_and_logout(client, cleanup):
    tokens, headers = _register_and_login(client, "refresh")
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    r = client.post("/auth/logout", json={"refresh_token": new_tokens["refresh_token"]})
    assert r.status_code == 200

    r = client.post("/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert r.status_code == 401


def test_password_reset_flow(client, cleanup):
    client.post("/auth/register", json={"email": _email("reset"), "password": "MyPassw0rd1", "display_name": "Reset"})
    r = client.post("/auth/password-reset/request", json={"email": _email("reset")})
    assert r.status_code == 200

    import main
    _, token = main._users_authentication._email_provider.sent_password_reset_emails[-1]

    r = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "NewPassw0rd1"})
    assert r.status_code == 200

    r = client.post("/auth/login", json={"email": _email("reset"), "password": "NewPassw0rd1"})
    assert r.status_code == 200


def test_update_profile(client, cleanup):
    _, headers = _register_and_login(client, "profile")
    r = client.patch("/users/me", json={"display_name": "New Name"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["display_name"] == "New Name"


def test_login_history_and_sessions(client, cleanup):
    _, headers = _register_and_login(client, "history")
    r = client.get("/users/me/login-history", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.get("/users/me/sessions", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_login_history_respects_a_custom_limit(client, cleanup):
    """API contract audit (pagination): the underlying repository
    already supported a `limit` param - it just wasn't reachable from
    the endpoint. A second login must be visible with limit=2."""
    _, headers = _register_and_login(client, "history-limit")
    r = client.post("/auth/login", json={"email": _email("history-limit"), "password": "MyPassw0rd1"})
    assert r.status_code == 200

    r = client.get("/users/me/login-history", params={"limit": 2}, headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_login_history_rejects_an_out_of_range_limit(client, cleanup):
    _, headers = _register_and_login(client, "history-badlimit")
    r = client.get("/users/me/login-history", params={"limit": 0}, headers=headers)
    assert r.status_code == 422
    r = client.get("/users/me/login-history", params={"limit": 10_000}, headers=headers)
    assert r.status_code == 422


def test_preferences_flow(client, cleanup):
    _, headers = _register_and_login(client, "prefs")
    r = client.get("/users/me/preferences", headers=headers)
    assert r.status_code == 200
    assert r.json()["theme"] == "system"

    r = client.put("/users/me/preferences", json={"theme": "dark", "language": "tr"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["theme"] == "dark"
    assert r.json()["language"] == "tr"


def test_api_key_lifecycle(client, cleanup):
    _, headers = _register_and_login(client, "apikey")

    r = client.post("/users/me/api-keys", json={"name": "CI Key", "scope": "read_only"}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    api_key_id = body["api_key"]["id"]
    assert body["key"].startswith("otk_")

    r = client.get("/users/me/api-keys", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.get(f"/users/me/api-keys/{api_key_id}/usage", headers=headers)
    assert r.status_code == 200
    assert r.json()["total_requests"] == 0

    r = client.post(f"/users/me/api-keys/{api_key_id}/rotate", headers=headers)
    assert r.status_code == 200
    new_key_id = r.json()["api_key"]["id"]
    assert new_key_id != api_key_id

    r = client.delete(f"/users/me/api-keys/{new_key_id}", headers=headers)
    assert r.status_code == 200


def test_organization_lifecycle(client, cleanup):
    _, headers = _register_and_login(client, "org-owner")

    r = client.post("/organizations", json={"name": "Test Org"}, headers=headers)
    assert r.status_code == 200, r.text
    org = r.json()
    org_id = org["id"]
    assert org["quotas"]["max_members"] == 10

    r = client.get("/organizations", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.get(f"/organizations/{org_id}", headers=headers)
    assert r.status_code == 200

    r = client.patch(f"/organizations/{org_id}", json={"name": "Renamed Org"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed Org"

    r = client.get(f"/organizations/{org_id}/usage", headers=headers)
    assert r.status_code == 200
    assert r.json()["usage"]["members"] == 1


def test_organization_requires_authentication(client, cleanup):
    r = client.post("/organizations", json={"name": "No Auth Org"})
    assert r.status_code == 401


def test_invitation_and_membership_flow(client, cleanup):
    _, owner_headers = _register_and_login(client, "inv-owner")
    org = client.post("/organizations", json={"name": "Inv Org"}, headers=owner_headers).json()
    org_id = org["id"]

    r = client.post(
        f"/organizations/{org_id}/invitations",
        json={"email": _email("inv-invitee"), "role": "admin"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    invitation_token = r.json()["token"]

    _, invitee_headers = _register_and_login(client, "inv-invitee")
    r = client.post("/organizations/invitations/accept", json={"token": invitation_token}, headers=invitee_headers)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    r = client.get(f"/organizations/{org_id}/members", headers=owner_headers)
    assert r.status_code == 200 and len(r.json()) == 2

    r = client.get(f"/organizations/{org_id}/audit-log", headers=owner_headers)
    assert r.status_code == 200
    assert len(r.json()) > 0

    r = client.get(f"/organizations/{org_id}/audit-log", params={"limit": 1}, headers=owner_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.get(f"/organizations/{org_id}/audit-log", params={"limit": 0}, headers=owner_headers)
    assert r.status_code == 422


def test_change_role_and_remove_member(client, cleanup):
    _, owner_headers = _register_and_login(client, "role-owner")
    org = client.post("/organizations", json={"name": "Role Org"}, headers=owner_headers).json()
    org_id = org["id"]

    invite = client.post(
        f"/organizations/{org_id}/invitations",
        json={"email": _email("role-member"), "role": "viewer"},
        headers=owner_headers,
    ).json()
    tokens, member_headers = _register_and_login(client, "role-member")
    client.post("/organizations/invitations/accept", json={"token": invite["token"]}, headers=member_headers)

    import main
    member_user_id = main._users_repository.get_user_by_email(_email("role-member")).id

    r = client.patch(
        f"/organizations/{org_id}/members/{member_user_id}/role", json={"role": "analyst"}, headers=owner_headers,
    )
    assert r.status_code == 200
    assert r.json()["role"] == "analyst"

    r = client.delete(f"/organizations/{org_id}/members/{member_user_id}", headers=owner_headers)
    assert r.status_code == 200


def test_team_lifecycle(client, cleanup):
    _, owner_headers = _register_and_login(client, "team-owner")
    org = client.post("/organizations", json={"name": "Team Org"}, headers=owner_headers).json()
    org_id = org["id"]

    r = client.post(f"/organizations/{org_id}/teams", json={"name": "Core Team"}, headers=owner_headers)
    assert r.status_code == 200
    team_id = r.json()["id"]

    r = client.get(f"/organizations/{org_id}/teams", headers=owner_headers)
    assert r.status_code == 200 and len(r.json()) == 1

    # owner adding themselves to the team they just created
    import main
    owner_user_id = main._users_repository.get_user_by_email(_email("team-owner")).id
    r = client.post(
        f"/organizations/{org_id}/teams/{team_id}/members", json={"user_id": owner_user_id}, headers=owner_headers,
    )
    assert r.status_code == 200

    r = client.get(f"/organizations/{org_id}/teams/{team_id}/members", headers=owner_headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.delete(f"/organizations/{org_id}/teams/{team_id}/members/{owner_user_id}", headers=owner_headers)
    assert r.status_code == 200

    r = client.delete(f"/organizations/{org_id}/teams/{team_id}", headers=owner_headers)
    assert r.status_code == 200
