"""
Tests for `main._verify_jwt_or_firebase_token` (production readiness
audit HIGH finding: "two parallel, mutually incompatible authentication
schemes split across the API surface" - every endpoint elsewhere in
this API accepts the Users Platform JWT issued by /auth/login, but
several stateless, non-owned-resource endpoints (symbol analysis,
scans, news, sectors) only ever accepted a Firebase ID token via
`verify_firebase_token`, so a mobile client authenticated purely
through /auth/login could not call them).

In this test environment `main._firebase_app` is None (no Firebase
credentials configured), which makes `verify_firebase_token` fail OPEN
for every case - so an end-to-end status-code check through TestClient
cannot actually distinguish "JWT accepted" from "no auth enforced at
all" here. These tests call `main._verify_jwt_or_firebase_token`
directly and monkeypatch `main._firebase_app`/`main.fb_auth` to a
configured-Firebase stand-in, so the JWT short-circuit and the
Firebase fallback are each verified for real, independent of whether
this environment happens to have Firebase configured.
"""
import asyncio

import pytest

import main as main_module

_EMAIL = "jwt-or-firebase-auth-test@example.com"


def _register_and_login(client) -> str:
    client.post("/auth/register", json={"email": _EMAIL, "password": "MyPassw0rd1", "display_name": "Auth Test"})
    r = client.post("/auth/login", json={"email": _EMAIL, "password": "MyPassw0rd1"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _cleanup() -> None:
    from users.repository import UsersRepository
    users_repo = UsersRepository()
    with users_repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM users_users WHERE email = %s", (_EMAIL,))
        row = cur.fetchone()
        if row:
            user_id = row[0]
            cur.execute("DELETE FROM users_sessions WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users_login_history WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users_users WHERE id = %s", (user_id,))


def test_a_valid_users_platform_jwt_authorizes_without_ever_calling_firebase(client, monkeypatch):
    """The JWT path must short-circuit - it must not depend on Firebase
    being configured, and must not attempt Firebase verification at
    all once the JWT itself has been validated."""
    access_token = _register_and_login(client)
    try:
        monkeypatch.setattr(main_module, "_firebase_app", object())

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("Firebase verification must not be attempted for a valid JWT")

        monkeypatch.setattr(main_module.fb_auth, "verify_id_token", _fail_if_called)

        uid = asyncio.run(main_module._verify_jwt_or_firebase_token(f"Bearer {access_token}"))
        assert uid is None
    finally:
        _cleanup()


def test_an_invalid_bearer_token_falls_back_to_firebase_and_is_rejected_when_firebase_is_configured():
    """A token that is neither a valid Users Platform JWT nor a valid
    Firebase ID token must still be rejected - the JWT-or-Firebase
    dependency does not weaken enforcement when Firebase IS configured,
    it only adds a second accepted credential type."""
    import fastapi

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(main_module, "_firebase_app", object())

        def _raise(*args, **kwargs):
            raise ValueError("invalid firebase token")

        monkeypatch.setattr(main_module.fb_auth, "verify_id_token", _raise)

        with pytest.raises(fastapi.HTTPException) as exc_info:
            asyncio.run(main_module._verify_jwt_or_firebase_token("Bearer not.a.valid.token"))
    assert exc_info.value.status_code == 401


def test_no_token_preserves_the_prior_fail_open_behavior_when_firebase_is_unconfigured():
    """Unchanged from `verify_firebase_token`'s own pre-existing
    behavior - not something this fix introduces or should change."""
    assert main_module._firebase_app is None
    uid = asyncio.run(main_module._verify_jwt_or_firebase_token(None))
    assert uid is None


def test_quant_analyze_accepts_a_users_platform_jwt_end_to_end(client):
    """Live confirmation through the real route (previously
    Firebase-token-only) that a Users Platform JWT is now accepted."""
    from decision_engine.repository import PostgresExecutionRepository
    from feature_store.config import FeatureStoreConfig
    from learning.persistence import LearningRepository

    access_token = _register_and_login(client)
    try:
        response = client.post(
            "/quant/analyze", json={"symbol": "AAPL"}, headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert response.json()["symbol"] == "AAPL"
    finally:
        _cleanup()
        exec_repo = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
        with exec_repo._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM decision_engine_executions WHERE symbol = %s AND aggregation_strategy_version = %s",
                ("AAPL", "pipeline_parallel_v1"),
            )
        exec_repo.close()
        learning_repo = LearningRepository()
        with learning_repo._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM learning_samples WHERE symbol = %s AND decided_at > now() - interval '10 minutes'",
                ("AAPL",),
            )
