"""
OptiTrade User & Organization Platform — organizations.

Quota enforcement for portfolios/watchlists bridges this package's
integer `user_id` to `portfolio.PortfolioService`/`watchlist.WatchlistService`,
whose `Portfolio.owner`/`Watchlist.owner` are plain strings (see
`get_resource_usage`) - every org member's `User.email` is used as the
owner key, since neither package has any concept of an integer user id
or an organization.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from users.authentication import generate_opaque_token, hash_token
from users.authorization import AuthorizationService
from users.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidTokenError,
    InvitationNotFoundError,
    LastOwnerError,
    MembershipNotFoundError,
    OrganizationNotFoundError,
    QuotaExceededError,
    UserNotFoundError,
)
from users.models import (
    AuditAction,
    AuditLogEntry,
    Invitation,
    InvitationStatus,
    Membership,
    Organization,
    OrganizationQuotas,
    Permission,
    Role,
)
from users.repository import UsersRepository
from users.validators import validate_email_format, validate_organization_name

logger = logging.getLogger(__name__)
_MODULE = "users.organizations"
_COMPONENT = "users"


class OrganizationService:
    def __init__(self, repository: UsersRepository, authorization: Optional[AuthorizationService] = None) -> None:
        self._repository = repository
        self._authorization = authorization or AuthorizationService(repository)

    def create_organization(
        self, name: str, owner_user_id: int, quotas: Optional[OrganizationQuotas] = None,
    ) -> Organization:
        started_at = time.perf_counter()
        validate_organization_name(name)
        if self._repository.get_user(owner_user_id) is None:
            raise UserNotFoundError(f"user {owner_user_id} not found")

        organization_id = self._repository.save_organization(
            Organization(name=name, owner_user_id=owner_user_id, quotas=quotas or OrganizationQuotas())
        )
        self._repository.save_membership(
            Membership(user_id=owner_user_id, organization_id=organization_id, role=Role.OWNER)
        )
        self._audit(owner_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"organization:{organization_id}", {"action": "created", "name": name})
        self._log_success("create_organization", started_at, organization_id=organization_id, owner_user_id=owner_user_id)
        return self._repository.get_organization(organization_id)

    def get_organization(self, organization_id: int) -> Organization:
        organization = self._repository.get_organization(organization_id)
        if organization is None:
            raise OrganizationNotFoundError(f"organization {organization_id} not found")
        return organization

    def list_organizations_for_user(self, user_id: int) -> List[Organization]:
        return self._repository.list_organizations_for_user(user_id)

    def update_organization(
        self, organization_id: int, actor_user_id: int, name: Optional[str] = None,
        quotas: Optional[OrganizationQuotas] = None,
    ) -> Organization:
        started_at = time.perf_counter()
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_ORGANIZATION)
        organization = self.get_organization(organization_id)
        if name is not None:
            validate_organization_name(name)
            organization.name = name
        if quotas is not None:
            organization.quotas = quotas
        self._repository.update_organization(organization)
        self._audit(actor_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"organization:{organization_id}", {"action": "updated"})
        self._log_success("update_organization", started_at, organization_id=organization_id)
        return self._repository.get_organization(organization_id)

    def delete_organization(self, organization_id: int, actor_user_id: int) -> None:
        started_at = time.perf_counter()
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_ORGANIZATION)
        self.get_organization(organization_id)
        self._repository.delete_organization(organization_id)
        self._log_success("delete_organization", started_at, organization_id=organization_id)

    # ── Membership / invitations ────────────────────────────────────────

    def list_members(self, organization_id: int) -> List[Membership]:
        return self._repository.list_memberships(organization_id)

    def invite_member(
        self, organization_id: int, actor_user_id: int, email: str, role: Role,
        team_id: Optional[int] = None,
    ) -> Tuple[Invitation, str]:
        started_at = time.perf_counter()
        validate_email_format(email)
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_MEMBERS)
        organization = self.get_organization(organization_id)

        email = email.strip().lower()
        existing_user = self._repository.get_user_by_email(email)
        if existing_user is not None and self._repository.get_membership(existing_user.id, organization_id) is not None:
            raise EmailAlreadyRegisteredError(f"{email} is already a member of organization {organization_id}")

        members = self._repository.list_memberships(organization_id)
        if len(members) >= organization.quotas.max_members:
            self._log_error("invite_member", QuotaExceededError(), started_at, organization_id=organization_id)
            raise QuotaExceededError(
                f"organization {organization_id} has reached its member quota ({organization.quotas.max_members})"
            )

        token = generate_opaque_token()
        invitation_id = self._repository.save_invitation(
            Invitation(
                organization_id=organization_id, team_id=team_id, email=email, role=role, invited_by=actor_user_id,
                token_hash=hash_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
        invitation = self._repository.get_invitation(invitation_id)
        self._audit(actor_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"invitation:{invitation_id}", {"action": "member_invited", "email": email, "role": role.value})
        self._log_success("invite_member", started_at, organization_id=organization_id, invitation_id=invitation_id)
        # The plaintext invitation token is returned exactly once, here -
        # only its hash is persisted (see `models.py` module docstring).
        return invitation, token

    def list_invitations(self, organization_id: int, actor_user_id: int) -> List[Invitation]:
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_MEMBERS)
        return self._repository.list_invitations(organization_id)

    def revoke_invitation(self, organization_id: int, actor_user_id: int, invitation_id: int) -> None:
        started_at = time.perf_counter()
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_MEMBERS)
        invitation = self._repository.get_invitation(invitation_id)
        if invitation is None or invitation.organization_id != organization_id:
            raise InvitationNotFoundError(f"invitation {invitation_id} not found in organization {organization_id}")
        self._repository.update_invitation_status(invitation_id, InvitationStatus.REVOKED)
        self._audit(actor_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"invitation:{invitation_id}", {"action": "invitation_revoked"})
        self._log_success("revoke_invitation", started_at, organization_id=organization_id, invitation_id=invitation_id)

    def accept_invitation(self, token: str, accepting_user_id: int) -> Membership:
        started_at = time.perf_counter()
        invitation = self._repository.get_invitation_by_token_hash(hash_token(token))
        now = datetime.now(timezone.utc)
        if invitation is None or invitation.status != InvitationStatus.PENDING or invitation.expires_at < now:
            self._log_error("accept_invitation", InvalidTokenError(), started_at)
            raise InvalidTokenError("invalid, expired, or already-used invitation token")

        user = self._repository.get_user(accepting_user_id)
        if user is None:
            raise UserNotFoundError(f"user {accepting_user_id} not found")
        if user.email != invitation.email:
            raise InvalidTokenError("this invitation was issued to a different email address")

        membership_id = self._repository.save_membership(
            Membership(
                user_id=accepting_user_id, organization_id=invitation.organization_id, role=invitation.role,
                invited_by=invitation.invited_by,
            )
        )
        if invitation.team_id is not None:
            from users.models import TeamMembership
            self._repository.add_team_member(TeamMembership(team_id=invitation.team_id, user_id=accepting_user_id))
        self._repository.update_invitation_status(invitation.id, InvitationStatus.ACCEPTED)
        self._audit(accepting_user_id, invitation.organization_id, AuditAction.ORGANIZATION_CHANGE, f"membership:{membership_id}", {"action": "invitation_accepted"})
        self._log_success("accept_invitation", started_at, organization_id=invitation.organization_id, user_id=accepting_user_id)
        return self._repository.get_membership(accepting_user_id, invitation.organization_id)

    def change_member_role(
        self, organization_id: int, actor_user_id: int, target_user_id: int, new_role: Role,
    ) -> Membership:
        started_at = time.perf_counter()
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_MEMBERS)
        membership = self._repository.get_membership(target_user_id, organization_id)
        if membership is None:
            raise MembershipNotFoundError(f"user {target_user_id} is not a member of organization {organization_id}")

        if membership.role == Role.OWNER and new_role != Role.OWNER:
            if self._authorization.is_last_owner(target_user_id, organization_id):
                raise LastOwnerError(f"cannot change role: organization {organization_id} would have no owner")

        membership.role = new_role
        self._repository.save_membership(membership)
        self._audit(actor_user_id, organization_id, AuditAction.ROLE_CHANGE, f"user:{target_user_id}", {"new_role": new_role.value})
        self._log_success("change_member_role", started_at, organization_id=organization_id, target_user_id=target_user_id)
        return self._repository.get_membership(target_user_id, organization_id)

    def remove_member(self, organization_id: int, actor_user_id: int, target_user_id: int) -> None:
        started_at = time.perf_counter()
        self._authorization.check_permission(actor_user_id, organization_id, Permission.MANAGE_MEMBERS)
        membership = self._repository.get_membership(target_user_id, organization_id)
        if membership is None:
            raise MembershipNotFoundError(f"user {target_user_id} is not a member of organization {organization_id}")

        if membership.role == Role.OWNER and self._authorization.is_last_owner(target_user_id, organization_id):
            raise LastOwnerError(f"cannot remove the last owner of organization {organization_id}")

        self._repository.delete_membership(target_user_id, organization_id)
        self._audit(actor_user_id, organization_id, AuditAction.ORGANIZATION_CHANGE, f"user:{target_user_id}", {"action": "member_removed"})
        self._log_success("remove_member", started_at, organization_id=organization_id, target_user_id=target_user_id)

    # ── Quotas ───────────────────────────────────────────────────────────

    def get_resource_usage(
        self, organization_id: int, portfolio_service=None, watchlist_service=None,
    ) -> Dict[str, int]:
        """Real resource counts for the organization's quotas. Member and
        team counts always come from this package's own tables.
        Portfolio/watchlist counts are computed by summing each member's
        owned resources (keyed by `User.email`, see module docstring) and
        are only included when the corresponding service is supplied -
        neither `portfolio` nor `watchlist` has any org concept of its
        own, so this package is the one that bridges them."""
        members = self._repository.list_memberships(organization_id)
        usage = {
            "members": len(members),
            "teams": len(self._repository.list_teams(organization_id)),
        }
        if portfolio_service is not None or watchlist_service is not None:
            emails = [
                user.email for user in
                (self._repository.get_user(m.user_id) for m in members)
                if user is not None
            ]
            if portfolio_service is not None:
                usage["portfolios"] = sum(len(portfolio_service.list_portfolios(email)) for email in emails)
            if watchlist_service is not None:
                usage["watchlists"] = sum(len(watchlist_service.list_watchlists(email)) for email in emails)
        return usage

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
