"""
OptiTrade User & Organization Platform — RBAC authorization.

Roles are organization-scoped only (see `users.models.Membership`'s
docstring) - `ROLE_PERMISSIONS` below is the single source of truth for
what each role can do. `get_current_user`/`require_permission` are
generic, reusable FastAPI dependencies: the intended integration point
for gating Decision Engine, Pipeline, and Feature Store endpoints, without
retrofitting authentication onto any existing route (no breaking changes).
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, FrozenSet, Optional

from fastapi import Depends, Header, HTTPException, status

from users.authentication import decode_access_token
from users.config import UsersConfig
from users.exceptions import (
    InvalidTokenError,
    MembershipNotFoundError,
    OrganizationNotFoundError,
    PermissionDeniedError,
)
from users.models import Permission, Role, User
from users.repository import UsersRepository

logger = logging.getLogger(__name__)

ROLE_PERMISSIONS: Dict[Role, FrozenSet[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: frozenset(
        {
            Permission.MANAGE_TEAMS,
            Permission.MANAGE_MEMBERS,
            Permission.MANAGE_API_KEYS,
            Permission.MANAGE_PORTFOLIOS,
            Permission.MANAGE_WATCHLISTS,
            Permission.MANAGE_ALERTS,
            Permission.VIEW_PORTFOLIOS,
            Permission.VIEW_WATCHLISTS,
            Permission.VIEW_ALERTS,
        }
    ),
    Role.PORTFOLIO_MANAGER: frozenset(
        {
            Permission.MANAGE_PORTFOLIOS,
            Permission.MANAGE_WATCHLISTS,
            Permission.MANAGE_ALERTS,
            Permission.VIEW_PORTFOLIOS,
            Permission.VIEW_WATCHLISTS,
            Permission.VIEW_ALERTS,
        }
    ),
    Role.ANALYST: frozenset(
        {Permission.VIEW_PORTFOLIOS, Permission.VIEW_WATCHLISTS, Permission.VIEW_ALERTS}
    ),
    Role.VIEWER: frozenset(
        {Permission.VIEW_PORTFOLIOS, Permission.VIEW_WATCHLISTS, Permission.VIEW_ALERTS}
    ),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


class AuthorizationService:
    """RBAC checks against a user's organization membership."""

    def __init__(self, repository: UsersRepository) -> None:
        self._repository = repository

    def get_role(self, user_id: int, organization_id: int) -> Role:
        membership = self._repository.get_membership(user_id, organization_id)
        if membership is None:
            # Every organization-scoped endpoint in main.py calls this (directly
            # or via check_permission) before touching the resource, so this is
            # the one place that decides 404-vs-403 for the entire org-scoped
            # API surface. A membership row can never exist for an organization
            # that doesn't exist, so "no membership" is ambiguous between "you
            # were never a member" and "this organization is gone" - distinguish
            # them here (matching the existing get-portfolio-then-authorize
            # pattern `_get_authorized_portfolio` in main.py already uses) so a
            # client can tell "not found" apart from "access denied" instead of
            # seeing 403 for both.
            if self._repository.get_organization(organization_id) is None:
                raise OrganizationNotFoundError(f"organization {organization_id} not found")
            raise MembershipNotFoundError(
                f"user {user_id} is not a member of organization {organization_id}"
            )
        return membership.role

    def check_permission(self, user_id: int, organization_id: int, permission: Permission) -> None:
        role = self.get_role(user_id, organization_id)
        if not has_permission(role, permission):
            raise PermissionDeniedError(
                f"role {role.value!r} does not grant permission {permission.value!r}"
            )

    def is_last_owner(self, user_id: int, organization_id: int) -> bool:
        owners = [m for m in self._repository.list_memberships(organization_id) if m.role == Role.OWNER]
        return len(owners) == 1 and owners[0].user_id == user_id


# ── FastAPI dependencies ──────────────────────────────────────────────────

def get_current_user(repository: UsersRepository, config: Optional[UsersConfig] = None) -> Callable[..., User]:
    """Builds a FastAPI dependency bound to the given repository/config -
    constructed once (mirrors how every other platform in this codebase
    wires its services once at startup and reuses them per request)."""

    config = config or UsersConfig.from_env()

    def _dependency(authorization: Optional[str] = Header(default=None)) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
        token = authorization.split(" ", 1)[1]
        try:
            user_id = decode_access_token(token, config)
        except InvalidTokenError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        user = repository.get_user(user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found or inactive")
        return user

    return _dependency


def require_permission(
    permission: Permission,
    repository: UsersRepository,
    current_user_dependency: Callable[..., User],
) -> Callable[..., User]:
    """Builds a FastAPI dependency that requires `current_user_dependency`
    to resolve a user AND that user to hold `permission` within the
    organization given by the request's `organization_id` parameter."""

    authorization_service = AuthorizationService(repository)

    def _dependency(organization_id: int, user: User = Depends(current_user_dependency)) -> User:
        try:
            authorization_service.check_permission(user.id, organization_id, permission)
        except OrganizationNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except (MembershipNotFoundError, PermissionDeniedError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return user

    return _dependency
