"""
OptiTrade User & Organization Platform — API keys.

Multiple keys per user, read-only/read-write scope, expiration, rotation,
revocation, and usage statistics. Only the SHA-256 hash of the key is
ever persisted; the plaintext key is returned to the caller exactly once,
at creation/rotation time (see `models.py`'s module docstring).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from users.audit import AuditService
from users.authorization import AuthorizationService
from users.exceptions import (
    APIKeyNotFoundError,
    InvalidTokenError,
    OrganizationNotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
)
from users.models import APIKey, APIKeyScope, APIKeyUsageRecord, APIKeyUsageStats, AuditAction, Permission
from users.repository import UsersRepository
from users.validators import validate_api_key_name

logger = logging.getLogger(__name__)
_MODULE = "users.api_keys"
_COMPONENT = "users"

_KEY_PREFIX = "otk"


def _generate_raw_key() -> str:
    return f"{_KEY_PREFIX}_{secrets.token_urlsafe(32)}"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class APIKeyService:
    def __init__(
        self,
        repository: UsersRepository,
        authorization: Optional[AuthorizationService] = None,
        audit: Optional[AuditService] = None,
    ) -> None:
        self._repository = repository
        self._authorization = authorization or AuthorizationService(repository)
        self._audit = audit or AuditService(repository)

    def create_api_key(
        self,
        user_id: int,
        name: str,
        scope: APIKeyScope = APIKeyScope.READ_ONLY,
        organization_id: Optional[int] = None,
        expires_in_seconds: Optional[int] = None,
    ) -> Tuple[APIKey, str]:
        started_at = time.perf_counter()
        validate_api_key_name(name)

        if organization_id is not None:
            self._authorization.check_permission(user_id, organization_id, Permission.MANAGE_API_KEYS)
            organization = self._repository.get_organization(organization_id)
            if organization is None:
                raise OrganizationNotFoundError(f"organization {organization_id} not found")
            existing = [k for k in self._repository.list_api_keys(user_id) if k.organization_id == organization_id]
            if len(existing) >= organization.quotas.max_api_keys:
                self._log_error("create_api_key", QuotaExceededError(), started_at, organization_id=organization_id)
                raise QuotaExceededError(
                    f"organization {organization_id} has reached its API key quota ({organization.quotas.max_api_keys})"
                )

        raw_key = _generate_raw_key()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
            if expires_in_seconds is not None else None
        )
        api_key_id = self._repository.save_api_key(
            APIKey(
                user_id=user_id, organization_id=organization_id, name=name, key_prefix=raw_key[:12],
                key_hash=_hash_key(raw_key), scope=scope, expires_at=expires_at,
            )
        )
        self._log_success("create_api_key", started_at, user_id=user_id, api_key_id=api_key_id)
        return self._repository.get_api_key(api_key_id), raw_key

    def get_api_key(self, api_key_id: int) -> APIKey:
        api_key = self._repository.get_api_key(api_key_id)
        if api_key is None:
            raise APIKeyNotFoundError(f"API key {api_key_id} not found")
        return api_key

    def list_api_keys(self, user_id: int) -> List[APIKey]:
        return self._repository.list_api_keys(user_id)

    def rotate_api_key(self, user_id: int, api_key_id: int) -> Tuple[APIKey, str]:
        started_at = time.perf_counter()
        old_key = self.get_api_key(api_key_id)
        if old_key.user_id != user_id:
            raise PermissionDeniedError(f"user {user_id} does not own API key {api_key_id}")

        old_key.revoked_at = datetime.now(timezone.utc)
        self._repository.update_api_key(old_key)

        raw_key = _generate_raw_key()
        expires_at = (
            datetime.now(timezone.utc) + (old_key.expires_at - old_key.created_at) if old_key.expires_at else None
        )
        new_key_id = self._repository.save_api_key(
            APIKey(
                user_id=old_key.user_id, organization_id=old_key.organization_id, name=old_key.name,
                key_prefix=raw_key[:12], key_hash=_hash_key(raw_key), scope=old_key.scope, expires_at=expires_at,
                rotated_from_id=old_key.id,
            )
        )
        self._log_success("rotate_api_key", started_at, user_id=user_id, old_api_key_id=api_key_id, new_api_key_id=new_key_id)
        return self._repository.get_api_key(new_key_id), raw_key

    def revoke_api_key(self, user_id: int, api_key_id: int) -> None:
        started_at = time.perf_counter()
        api_key = self.get_api_key(api_key_id)
        if api_key.user_id != user_id:
            raise PermissionDeniedError(f"user {user_id} does not own API key {api_key_id}")
        api_key.revoked_at = datetime.now(timezone.utc)
        self._repository.update_api_key(api_key)
        self._log_success("revoke_api_key", started_at, user_id=user_id, api_key_id=api_key_id)

    def authenticate(self, raw_key: str) -> APIKey:
        api_key = self._repository.get_api_key_by_hash(_hash_key(raw_key))
        now = datetime.now(timezone.utc)
        if (
            api_key is None
            or api_key.revoked_at is not None
            or (api_key.expires_at is not None and api_key.expires_at < now)
        ):
            raise InvalidTokenError("invalid, expired, or revoked API key")
        return api_key

    def record_usage(self, api_key_id: int, endpoint: str, status_code: int) -> None:
        self._repository.save_api_key_usage(
            APIKeyUsageRecord(api_key_id=api_key_id, endpoint=endpoint, status_code=status_code)
        )
        api_key = self._repository.get_api_key(api_key_id)
        if api_key is not None:
            api_key.last_used_at = datetime.now(timezone.utc)
            self._repository.update_api_key(api_key)
            self._audit.record(
                AuditAction.API_KEY_USAGE, actor_user_id=api_key.user_id, organization_id=api_key.organization_id,
                target=f"api_key:{api_key_id}", details={"endpoint": endpoint, "status_code": str(status_code)},
            )

    def get_usage_stats(self, api_key_id: int) -> APIKeyUsageStats:
        api_key = self.get_api_key(api_key_id)
        records = self._repository.list_api_key_usage(api_key_id, limit=10_000)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        return APIKeyUsageStats(
            api_key_id=api_key_id,
            total_requests=len(records),
            requests_last_24h=sum(1 for r in records if r.occurred_at >= cutoff),
            last_used_at=api_key.last_used_at,
            error_count=sum(1 for r in records if r.status_code >= 400),
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
