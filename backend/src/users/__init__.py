"""
OptiTrade User & Organization Platform.

Authentication (JWT access tokens, opaque revocable refresh tokens,
PBKDF2 password hashing, session management, login history, device
tracking, password reset workflow, email verification abstraction -
`authentication.py`/`sessions.py`); RBAC authorization scoped to
organization membership (`authorization.py`); multi-organization,
multi-team structure with member invitations and quotas
(`organizations.py`/`teams.py`); API keys with scopes, expiration,
rotation, revocation, and usage statistics (`api_keys.py`); user
preferences with real `portfolio`/`watchlist` ownership validation
(`preferences.py`); and an audit log covering login, logout, api key
usage, role changes, organization changes, and portfolio permission
changes (`audit.py`).

Integrates directly with `portfolio`/`watchlist` (preferences ownership,
organization quotas) and exposes generic, reusable FastAPI dependencies
(`authorization.get_current_user`/`require_permission`) as the intended
gate for Decision Engine/Pipeline/Feature Store endpoints - never
`research_lab`, guarded the same way every other production package
already is (see `tests/test_research_isolation.py`).
"""
from users.api_keys import APIKeyService
from users.audit import AuditService
from users.authentication import AuthenticationService, InMemoryEmailVerificationProvider
from users.authorization import AuthorizationService, get_current_user, require_permission
from users.organizations import OrganizationService
from users.preferences import PreferencesService
from users.repository import UsersRepository
from users.service import UserService
from users.sessions import SessionService
from users.teams import TeamService

__all__ = [
    "UsersRepository",
    "UserService",
    "AuthenticationService",
    "InMemoryEmailVerificationProvider",
    "AuthorizationService",
    "get_current_user",
    "require_permission",
    "SessionService",
    "OrganizationService",
    "TeamService",
    "APIKeyService",
    "PreferencesService",
    "AuditService",
]
