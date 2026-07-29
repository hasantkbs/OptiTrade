"""
OptiTrade User & Organization Platform — top-level user facade.

The entry point other platforms (Decision Engine, Pipeline, Feature
Store, ...) should use to resolve a user record; registration itself is
delegated to `AuthenticationService` (the single owner of password
hashing / email-verification side effects).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from users.authentication import AuthenticationService
from users.exceptions import UserNotFoundError
from users.models import User
from users.repository import UsersRepository
from users.validators import validate_not_blank

logger = logging.getLogger(__name__)
_MODULE = "users.service"
_COMPONENT = "users"


class UserService:
    def __init__(self, repository: UsersRepository, authentication: Optional[AuthenticationService] = None) -> None:
        self._repository = repository
        self._authentication = authentication or AuthenticationService(repository)

    def register(self, email: str, password: str, display_name: str) -> User:
        return self._authentication.register(email, password, display_name)

    def get_by_id(self, user_id: int) -> User:
        user = self._repository.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"user {user_id} not found")
        return user

    def get_by_email(self, email: str) -> User:
        user = self._repository.get_user_by_email(email)
        if user is None:
            raise UserNotFoundError(f"{email} not found")
        return user

    def update_profile(self, user_id: int, display_name: Optional[str] = None) -> User:
        started_at = time.perf_counter()
        user = self.get_by_id(user_id)
        if display_name is not None:
            validate_not_blank(display_name, "display name")
            user.display_name = display_name
        self._repository.update_user(user)
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="update_profile", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, user_id=user_id,
        )
        return self.get_by_id(user_id)

    def deactivate(self, user_id: int) -> User:
        started_at = time.perf_counter()
        user = self.get_by_id(user_id)
        user.is_active = False
        self._repository.update_user(user)
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="deactivate", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, user_id=user_id,
        )
        return self.get_by_id(user_id)

    def reactivate(self, user_id: int) -> User:
        started_at = time.perf_counter()
        user = self.get_by_id(user_id)
        user.is_active = True
        self._repository.update_user(user)
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="reactivate", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, user_id=user_id,
        )
        return self.get_by_id(user_id)
