"""
OptiTrade User & Organization Platform — domain models.

Every stored secret (refresh tokens, API keys, password reset tokens,
invitation tokens) is persisted only as a salted hash - the plaintext
value is returned to the caller exactly once, at creation time, and
never stored anywhere (see `authentication.py`/`api_keys.py`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


# ── RBAC ─────────────────────────────────────────────────────────────────


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    PORTFOLIO_MANAGER = "portfolio_manager"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Permission(str, Enum):
    MANAGE_ORGANIZATION = "manage_organization"
    MANAGE_TEAMS = "manage_teams"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_API_KEYS = "manage_api_keys"
    MANAGE_PORTFOLIOS = "manage_portfolios"
    MANAGE_WATCHLISTS = "manage_watchlists"
    MANAGE_ALERTS = "manage_alerts"
    VIEW_PORTFOLIOS = "view_portfolios"
    VIEW_WATCHLISTS = "view_watchlists"
    VIEW_ALERTS = "view_alerts"


# ── Users ────────────────────────────────────────────────────────────────


class User(BaseModel):
    id: Optional[int] = None
    email: str
    password_hash: str
    display_name: str
    is_email_verified: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class DeviceInfo(BaseModel):
    user_agent: str = ""
    ip_address: str = ""
    device_name: str = ""


# ── Sessions / login history (requirement: session management, login
# history, device tracking) ─────────────────────────────────────────────


class Session(BaseModel):
    id: Optional[int] = None
    user_id: int
    refresh_token_hash: str
    device: DeviceInfo = Field(default_factory=DeviceInfo)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class LoginHistoryEntry(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    email: str
    success: bool
    failure_reason: Optional[str] = None
    device: DeviceInfo = Field(default_factory=DeviceInfo)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PasswordResetToken(BaseModel):
    id: Optional[int] = None
    user_id: int
    token_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    used_at: Optional[datetime] = None


class TokenPair(BaseModel):
    """The result of a successful login/refresh - JWT access token
    (stateless, short-lived) plus an opaque, server-side-revocable
    refresh token (see `Session`)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., gt=0)


# ── Organizations / teams / membership (requirement: multiple
# organizations, multiple teams, member invitations, permissions,
# quotas) ────────────────────────────────────────────────────────────────


class OrganizationQuotas(BaseModel):
    max_members: int = Field(default=10, gt=0)
    max_teams: int = Field(default=5, gt=0)
    max_portfolios: int = Field(default=20, gt=0)
    max_watchlists: int = Field(default=20, gt=0)
    max_api_keys: int = Field(default=10, gt=0)


class Organization(BaseModel):
    id: Optional[int] = None
    name: str
    owner_user_id: int
    quotas: OrganizationQuotas = Field(default_factory=OrganizationQuotas)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class Team(BaseModel):
    id: Optional[int] = None
    organization_id: int
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class Membership(BaseModel):
    """A user's organization-level role - RBAC roles are scoped to the
    organization, not to any one team. Team assignment is a separate,
    role-less concept (see `TeamMembership`)."""

    id: Optional[int] = None
    user_id: int
    organization_id: int
    role: Role
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    invited_by: Optional[int] = None


class TeamMembership(BaseModel):
    id: Optional[int] = None
    team_id: int
    user_id: int
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class Invitation(BaseModel):
    id: Optional[int] = None
    organization_id: int
    team_id: Optional[int] = None
    email: str
    role: Role
    invited_by: int
    token_hash: str
    status: InvitationStatus = InvitationStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return value.strip().lower()


# ── API keys (requirement: multiple keys, read-only/read-write,
# expiration, rotation, revocation, usage statistics) ───────────────────


class APIKeyScope(str, Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class APIKey(BaseModel):
    id: Optional[int] = None
    user_id: int
    organization_id: Optional[int] = None
    name: str
    key_prefix: str
    key_hash: str
    scope: APIKeyScope = APIKeyScope.READ_ONLY
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    rotated_from_id: Optional[int] = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class APIKeyUsageRecord(BaseModel):
    id: Optional[int] = None
    api_key_id: int
    endpoint: str
    status_code: int
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class APIKeyUsageStats(BaseModel):
    api_key_id: int
    total_requests: int = Field(..., ge=0)
    requests_last_24h: int = Field(..., ge=0)
    last_used_at: Optional[datetime] = None
    error_count: int = Field(..., ge=0)


# ── Preferences (requirement: theme, language, notifications,
# dashboard layout, default portfolio, default watchlist) ───────────────


class Theme(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class UserPreferences(BaseModel):
    user_id: int
    theme: Theme = Theme.SYSTEM
    language: str = "en"
    notification_settings: Dict[str, bool] = Field(
        default_factory=lambda: {"email": True, "push": True, "sms": False}
    )
    dashboard_layout: Dict[str, Any] = Field(default_factory=dict)
    default_portfolio_id: Optional[int] = None
    default_watchlist_id: Optional[int] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Audit (requirement: log every login, logout, api key usage, role
# changes, organization changes, portfolio permission changes) ──────────


class AuditAction(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    API_KEY_USAGE = "api_key_usage"
    ROLE_CHANGE = "role_change"
    ORGANIZATION_CHANGE = "organization_change"
    PORTFOLIO_PERMISSION_CHANGE = "portfolio_permission_change"


class AuditLogEntry(BaseModel):
    id: Optional[int] = None
    actor_user_id: Optional[int] = None
    organization_id: Optional[int] = None
    action: AuditAction
    target: str = ""
    details: Dict[str, str] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
