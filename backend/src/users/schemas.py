"""
OptiTrade User & Organization Platform — FastAPI request/response schemas.

Kept deliberately separate from `models.py` (the internal domain models):
these are the API-facing shapes. Every response schema uses
`from_attributes=True` so it can be built directly from the matching
domain model via `Response.model_validate(domain_object)`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from users.models import (
    APIKeyScope,
    AuditAction,
    InvitationStatus,
    OrganizationQuotas,
    Role,
    Theme,
)


class _ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Authentication ───────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class PasswordResetRequestSchema(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class TokenPairResponse(_ResponseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(_ResponseModel):
    id: int
    email: str
    display_name: str
    is_email_verified: bool
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None


class LoginHistoryEntryResponse(_ResponseModel):
    id: int
    user_id: Optional[int] = None
    email: str
    success: bool
    failure_reason: Optional[str] = None
    occurred_at: datetime


class SessionResponse(_ResponseModel):
    id: int
    user_id: int
    created_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


# ── Organizations / teams ─────────────────────────────────────────────────

class OrganizationQuotasSchema(BaseModel):
    max_members: int = Field(default=10, gt=0)
    max_teams: int = Field(default=5, gt=0)
    max_portfolios: int = Field(default=20, gt=0)
    max_watchlists: int = Field(default=20, gt=0)
    max_api_keys: int = Field(default=10, gt=0)


class CreateOrganizationRequest(BaseModel):
    name: str
    quotas: Optional[OrganizationQuotasSchema] = None


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = None
    quotas: Optional[OrganizationQuotasSchema] = None


class OrganizationResponse(_ResponseModel):
    id: int
    name: str
    owner_user_id: int
    quotas: OrganizationQuotas
    created_at: datetime


class ResourceUsageResponse(BaseModel):
    usage: Dict[str, int]
    quotas: OrganizationQuotas


class CreateTeamRequest(BaseModel):
    name: str


class TeamResponse(_ResponseModel):
    id: int
    organization_id: int
    name: str
    created_at: datetime


class AddTeamMemberRequest(BaseModel):
    user_id: int


class TeamMembershipResponse(_ResponseModel):
    id: int
    team_id: int
    user_id: int
    added_at: datetime


class InviteMemberRequest(BaseModel):
    email: str
    role: Role
    team_id: Optional[int] = None


class InvitationResponse(_ResponseModel):
    id: int
    organization_id: int
    team_id: Optional[int] = None
    email: str
    role: Role
    invited_by: int
    status: InvitationStatus
    created_at: datetime
    expires_at: datetime


class InvitationCreatedResponse(BaseModel):
    invitation: InvitationResponse
    token: str


class AcceptInvitationRequest(BaseModel):
    token: str


class ChangeRoleRequest(BaseModel):
    role: Role


class MembershipResponse(_ResponseModel):
    id: int
    user_id: int
    organization_id: int
    role: Role
    joined_at: datetime
    invited_by: Optional[int] = None


# ── API keys ─────────────────────────────────────────────────────────────

class CreateAPIKeyRequest(BaseModel):
    name: str
    scope: APIKeyScope = APIKeyScope.READ_ONLY
    organization_id: Optional[int] = None
    expires_in_seconds: Optional[int] = None


class APIKeyResponse(_ResponseModel):
    id: int
    user_id: int
    organization_id: Optional[int] = None
    name: str
    key_prefix: str
    scope: APIKeyScope
    created_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    rotated_from_id: Optional[int] = None


class APIKeyCreatedResponse(BaseModel):
    api_key: APIKeyResponse
    key: str


class APIKeyUsageStatsResponse(_ResponseModel):
    api_key_id: int
    total_requests: int
    requests_last_24h: int
    last_used_at: Optional[datetime] = None
    error_count: int


# ── Preferences ──────────────────────────────────────────────────────────

class UpdatePreferencesRequest(BaseModel):
    theme: Optional[Theme] = None
    language: Optional[str] = None
    notification_settings: Optional[Dict[str, bool]] = None
    dashboard_layout: Optional[Dict[str, Any]] = None
    default_portfolio_id: Optional[int] = None
    default_watchlist_id: Optional[int] = None


class PreferencesResponse(_ResponseModel):
    user_id: int
    theme: Theme
    language: str
    notification_settings: Dict[str, bool]
    dashboard_layout: Dict[str, Any]
    default_portfolio_id: Optional[int] = None
    default_watchlist_id: Optional[int] = None
    updated_at: datetime


# ── Audit ────────────────────────────────────────────────────────────────

class AuditLogEntryResponse(_ResponseModel):
    id: int
    actor_user_id: Optional[int] = None
    organization_id: Optional[int] = None
    action: AuditAction
    target: str
    details: Dict[str, str]
    ip_address: Optional[str] = None
    occurred_at: datetime
