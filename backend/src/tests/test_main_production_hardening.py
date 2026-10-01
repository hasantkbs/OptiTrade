"""
Focused regression tests for SERVER STEP 5's two environment-conditional
main.py behaviors: public docs/OpenAPI disabled in production, and
opt-in TrustedHostMiddleware.

Both are decided at module import time (FastAPI(openapi_url=...) and
app.add_middleware(...) run when main.py is first imported, not inside
a function), so - matching this project's existing convention for
import-time-conditional config (see users/config.py's own ephemeral-
JWT-secret path, verified live rather than via module reload in
SERVER STEP 3) - these run `import main` in a fresh subprocess per
environment instead of monkeypatching os.environ and reloading the
already-imported module in-process, which would leave every other
test in the session that also imports `main` sharing one mutated
module object.
"""
import json
import os
import subprocess
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _import_main_and_report(extra_env: dict) -> dict:
    """Fresh Python subprocess, `import main`, report the two
    SERVER STEP 5 conditionals as JSON on stdout. A real Postgres/Redis
    (this project's established real-infrastructure testing
    convention) is required - `main.py` connects to both at import-
    adjacent startup regardless of what's being tested here."""
    env = dict(os.environ)
    env.update(extra_env)
    code = (
        "import main, json; "
        "print(json.dumps({"
        "'openapi_url': main.app.openapi_url, "
        "'has_trusted_host_middleware': any("
        "m.cls.__name__ == 'TrustedHostMiddleware' for m in main.app.user_middleware"
        ")"
        "}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"subprocess import failed:\n{result.stdout}\n{result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_openapi_stays_enabled_when_environment_is_not_production():
    report = _import_main_and_report({"ENVIRONMENT": ""})
    assert report["openapi_url"] == "/openapi.json"


def test_openapi_is_disabled_when_environment_is_production():
    report = _import_main_and_report({
        "ENVIRONMENT": "production",
        "USERS_JWT_SECRET": "a" * 32,
    })
    assert report["openapi_url"] is None


def test_trusted_host_middleware_is_not_added_when_allowed_hosts_is_unset():
    report = _import_main_and_report({"ALLOWED_HOSTS": ""})
    assert report["has_trusted_host_middleware"] is False


def test_trusted_host_middleware_is_added_when_allowed_hosts_is_set():
    report = _import_main_and_report({"ALLOWED_HOSTS": "api.example.com"})
    assert report["has_trusted_host_middleware"] is True
