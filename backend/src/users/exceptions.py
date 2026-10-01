"""OptiTrade User & Organization Platform — exception types."""
from __future__ import annotations


class UserPlatformError(Exception):
    """Base class for all User & Organization Platform errors."""


class UserPlatformPersistenceError(UserPlatformError):
    """Raised when a record could not be read from or written to storage."""


class ValidationFailedError(UserPlatformError):
    """Raised for structurally invalid input (bad email, weak password,
    blank name, ...)."""


class UserNotFoundError(UserPlatformError):
    pass


class EmailAlreadyRegisteredError(UserPlatformError):
    pass


class InvalidCredentialsError(UserPlatformError):
    """Raised for a wrong password, an unknown email, or a deactivated
    account - deliberately the same error for all three, so a caller
    can never distinguish "no such account" from "wrong password"."""


class InvalidTokenError(UserPlatformError):
    """Raised for an invalid/expired/revoked JWT, refresh token,
    password reset token, or invitation token."""


class OrganizationNotFoundError(UserPlatformError):
    pass


class TeamNotFoundError(UserPlatformError):
    pass


class MembershipNotFoundError(UserPlatformError):
    pass


class InvitationNotFoundError(UserPlatformError):
    pass


class APIKeyNotFoundError(UserPlatformError):
    pass


class PermissionDeniedError(UserPlatformError):
    pass


class QuotaExceededError(UserPlatformError):
    pass


class LastOwnerError(UserPlatformError):
    """Raised when an operation would leave an organization with no
    OWNER at all."""
