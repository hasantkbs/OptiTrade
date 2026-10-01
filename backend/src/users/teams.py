"""
OptiTrade User & Organization Platform — teams.

Teams are a pure grouping concept within an organization - RBAC roles
live on `Membership` (organization-scoped), never on `TeamMembership`
(see `users.models` module docstring for the reasoning). Adding someone
to a team never changes their permissions.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from users.authorization import AuthorizationService
from users.exceptions import (
    MembershipNotFoundError,
    OrganizationNotFoundError,
    QuotaExceededError,
    TeamNotFoundError,
)
from users.models import AuditAction, AuditLogEntry, Permission, Team, TeamMembership
from users.repository import UsersRepository
from users.validators import validate_team_name

logger = logging.getLogger(__name__)
_MODULE = "users.teams"
_COMPONENT = "users"


class TeamService:
    def __init__(self, repository: UsersRepository, authorization: Optional[AuthorizationService] = None) -> None:
        self._repository = repository
        self._authorization = authorization or AuthorizationService(repository)

    def create_team(self, organization_id: int, actor_user_id: int, name: str) -> Team:
        started_at = time.perf_counter()
        validate_team_name(name)
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_TEAMS)

        organization = self._repository.get_organization(organization_id)
        if organization is None:
            raise OrganizationNotFoundError(f"organization {organization_id} not found")
        existing = self._repository.list_teams(organization_id)
        if len(existing) >= organization.quotas.max_teams:
            self._log_error("create_team", QuotaExceededError(), started_at, organization_id=organization_id)
            raise QuotaExceededError(
                f"organization {organization_id} has reached its team quota ({organization.quotas.max_teams})"
            )

        team_id = self._repository.save_team(Team(organization_id=organization_id, name=name))
        team = self._repository.get_team(team_id)
        self._audit(actor_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"team:{team_id}", {"action": "team_created", "name": name})
        self._log_success("create_team", started_at, organization_id=organization_id, team_id=team_id)
        return team

    def get_team(self, team_id: int) -> Team:
        team = self._repository.get_team(team_id)
        if team is None:
            raise TeamNotFoundError(f"team {team_id} not found")
        return team

    def list_teams(self, organization_id: int) -> List[Team]:
        return self._repository.list_teams(organization_id)

    def delete_team(self, organization_id: int, actor_user_id: int, team_id: int) -> None:
        started_at = time.perf_counter()
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_TEAMS)
        team = self.get_team(team_id)
        if team.organization_id != organization_id:
            raise TeamNotFoundError(f"team {team_id} does not belong to organization {organization_id}")
        self._repository.delete_team(team_id)
        self._audit(actor_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"team:{team_id}", {"action": "team_deleted"})
        self._log_success("delete_team", started_at, organization_id=organization_id, team_id=team_id)

    def add_member(self, organization_id: int, actor_user_id: int, team_id: int, user_id: int) -> TeamMembership:
        started_at = time.perf_counter()
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_TEAMS)
        team = self.get_team(team_id)
        if team.organization_id != organization_id:
            raise TeamNotFoundError(f"team {team_id} does not belong to organization {organization_id}")
        if self._repository.get_membership(user_id, organization_id) is None:
            raise MembershipNotFoundError(
                f"user {user_id} is not a member of organization {organization_id}, cannot join team {team_id}"
            )

        membership_id = self._repository.add_team_member(TeamMembership(team_id=team_id, user_id=user_id))
        self._audit(actor_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"team:{team_id}", {"action": "member_added", "user_id": str(user_id)})
        self._log_success("add_member", started_at, organization_id=organization_id, team_id=team_id, user_id=user_id)
        return TeamMembership(id=membership_id, team_id=team_id, user_id=user_id, added_at=datetime.now(timezone.utc))

    def remove_member(self, organization_id: int, actor_user_id: int, team_id: int, user_id: int) -> None:
        started_at = time.perf_counter()
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_TEAMS)
        team = self.get_team(team_id)
        if team.organization_id != organization_id:
            raise TeamNotFoundError(f"team {team_id} does not belong to organization {organization_id}")
        self._repository.remove_team_member(team_id, user_id)
        self._audit(actor_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"team:{team_id}", {"action": "member_removed", "user_id": str(user_id)})
        self._log_success("remove_member", started_at, organization_id=organization_id, team_id=team_id, user_id=user_id)

    def list_members(self, team_id: int) -> List[TeamMembership]:
        return self._repository.list_team_members(team_id)

    def _audit(self, actor_user_id: int, organization_id: int, action: AuditAction, target: str, details: dict) -> None:
        self._repository.save_audit_entry(
            AuditLogEntry(
                actor_user_id=actor_user_id, organization_id=organization_id, action=action, target=target,
                details={key: str(value) for key, value in details.items()},
            )
        )

    def _log_success(self, operation: str, started_at: float, **extra) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, **extra,
        )

    def _log_error(self, operation: str, exc: Exception, started_at: float, **extra) -> None:
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation=operation, status=STATUS_ERROR,
            error_type=type(exc).__name__, execution_time_ms=(time.perf_counter() - started_at) * 1000,
            level=logging.ERROR, **extra,
        )
