"""
OptiTrade User & Organization Platform — audit log.

Records and queries the audit trail required for: login, logout, api key
usage, role changes, organization changes, and portfolio permission
changes. `authentication.py` and `organizations.py` write their own
entries directly via `UsersRepository.save_audit_entry` (they already
hold a repository reference); this module is the query-facing facade
plus the one write path (`record`) used by `api_keys.py` for usage
logging.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from users.models import AuditAction, AuditLogEntry
from users.repository import UsersRepository

logger = logging.getLogger(__name__)
_MODULE = "users.audit"
_COMPONENT = "users"


class AuditService:
    def __init__(self, repository: UsersRepository) -> None:
        self._repository = repository

    def record(
        self,
        action: AuditAction,
        actor_user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        target: str = "",
        details: Optional[Dict[str, str]] = None,
        ip_address: Optional[str] = None,
    ) -> int:
        started_at = time.perf_counter()
        entry_id = self._repository.save_audit_entry(
            AuditLogEntry(
                actor_user_id=actor_user_id, organization_id=organization_id, action=action, target=target,
                details=details or {}, ip_address=ip_address,
            )
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="record", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, action=action.value, entry_id=entry_id,
        )
        return entry_id

    def list_for_organization(self, organization_id: int, limit: int = 100) -> List[AuditLogEntry]:
        return self._repository.list_audit_log(organization_id=organization_id, limit=limit)

    def list_for_user(self, actor_user_id: int, limit: int = 100) -> List[AuditLogEntry]:
        return self._repository.list_audit_log(actor_user_id=actor_user_id, limit=limit)
