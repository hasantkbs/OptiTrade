"""
Regression tests for the production audit's "Auth endpoints have zero
rate limiting" Critical finding: /auth/register, /auth/login,
/auth/refresh, /auth/logout, /auth/password-reset/request, and
/auth/password-reset/confirm previously had no `@limiter.limit(...)`
decorator at all (every other endpoint in main.py already uses one),
so nothing stopped unlimited credential-stuffing/brute-force/mass-
registration attempts against them.

`main.limiter` (slowapi) tracks request counts in a single process-wide
in-memory store keyed by client IP - shared across every test in this
whole pytest session (the TestClient always presents the same fake IP).
`limiter.reset()` clears that store before each test here so this
file's own volume can't be thrown off by unrelated tests that also
exercise /auth/register or /auth/login (see test_main_users_endpoints.py
and friends), and so this file doesn't eat into their budget either.
"""
import main


def _reset_limiter():
    main.limiter.reset()


def test_login_endpoint_is_rate_limited(client):
    _reset_limiter()
    # /auth/login is configured for 30/minute - the 31st call in the
    # same window must be rejected before it even reaches auth logic.
    responses = [
        client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
        for _ in range(31)
    ]
    assert all(r.status_code in (401, 429) for r in responses[:30])
    assert responses[30].status_code == 429


def test_register_endpoint_is_rate_limited(client):
    _reset_limiter()
    # /auth/register is configured for 20/minute.
    responses = [
        client.post(
            "/auth/register",
            json={"email": f"rl-test-{i}@example.com", "password": "MyPassw0rd1", "display_name": "x"},
        )
        for i in range(21)
    ]
    assert responses[20].status_code == 429
    # cleanup: delete any users this test actually managed to create
    from users.repository import UsersRepository
    repo = UsersRepository()
    with repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users_users WHERE email LIKE 'rl-test-%@example.com'")


def test_password_reset_request_endpoint_is_rate_limited(client):
    _reset_limiter()
    # /auth/password-reset/request is configured for 5/minute.
    responses = [
        client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})
        for _ in range(6)
    ]
    assert responses[5].status_code == 429


def test_auth_endpoints_all_carry_a_rate_limit_decorator():
    # Structural guard covering all six /auth/* routes at once - only
    # three are exercised above with real 429s (doing that for all six
    # would burn more of the shared in-memory rate-limit budget other
    # test files rely on, for no extra signal). `@limiter.limit(...)`
    # wraps the endpoint via `functools.wraps` (leaves `__wrapped__`
    # pointing at the original function) and the wrapper's own bytecode
    # references slowapi internals like `_check_request_limit` and
    # `view_rate_limit` - both are reliable, cheap-to-check fingerprints
    # that the decorator was actually applied, without any HTTP calls.
    auth_paths = {
        "/auth/register", "/auth/login", "/auth/refresh", "/auth/logout",
        "/auth/password-reset/request", "/auth/password-reset/confirm",
    }
    decorated = set()
    for route in main.app.routes:
        path = getattr(route, "path", None)
        if path in auth_paths:
            has_wrapped = getattr(route.endpoint, "__wrapped__", None) is not None
            references_slowapi_internals = "_check_request_limit" in route.endpoint.__code__.co_names
            if has_wrapped and references_slowapi_internals:
                decorated.add(path)
    assert decorated == auth_paths, f"missing rate limiting on: {auth_paths - decorated}"
