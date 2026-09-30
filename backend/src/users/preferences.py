"""
OptiTrade User & Organization Platform — preferences.

Theme, language, notification settings, dashboard layout, default
portfolio, default watchlist. Default portfolio/watchlist are validated
against real ownership when `portfolio_service`/`watchlist_service` are
supplied (both keyed by `Portfolio.owner`/`Watchlist.owner`, which is
`User.email` - see `organizations.py`'s module docstring for the same
bridging pattern).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from users.exceptions import PermissionDeniedError, UserNotFoundError, ValidationFailedError
from users.models import Theme, UserPreferences
from users.repository import UsersRepository

logger = logging.getLogger(__name__)
_MODULE = "users.preferences"
_COMPONENT = "users"


class PreferencesService:
    def __init__(self, repository: UsersRepository, portfolio_service=None, watchlist_service=None) -> None:
        self._repository = repository
        self._portfolio_service = portfolio_service
        self._watchlist_service = watchlist_service

    def get_preferences(self, user_id: int) -> UserPreferences:
        preferences = self._repository.get_preferences(user_id)
        if preferences is not None:
            return preferences
        if self._repository.get_user(user_id) is None:
            raise UserNotFoundError(f"user {user_id} not found")
        return UserPreferences(user_id=user_id)

    def update_preferences(
        self,
        user_id: int,
        theme: Optional[Theme] = None,
        language: Optional[str] = None,
        notification_settings: Optional[Dict[str, bool]] = None,
        dashboard_layout: Optional[Dict[str, Any]] = None,
        default_portfolio_id: Optional[int] = None,
        default_watchlist_id: Optional[int] = None,
    ) -> UserPreferences:
        started_at = time.perf_counter()
        user = self._repository.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"user {user_id} not found")

        preferences = self.get_preferences(user_id)
        if theme is not None:
            preferences.theme = theme
        if language is not None:
            preferences.language = language
        if notification_settings is not None:
            preferences.notification_settings = notification_settings
        if dashboard_layout is not None:
            preferences.dashboard_layout = dashboard_layout
        if default_portfolio_id is not None:
            self._validate_portfolio_ownership(user.email, default_portfolio_id)
            preferences.default_portfolio_id = default_portfolio_id
        if default_watchlist_id is not None:
            self._validate_watchlist_ownership(user.email, default_watchlist_id)
            preferences.default_watchlist_id = default_watchlist_id

        preferences.updated_at = datetime.now(timezone.utc)
        self._repository.save_preferences(preferences)
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="update_preferences", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, user_id=user_id,
        )
        return preferences

    def _validate_portfolio_ownership(self, owner_email: str, portfolio_id: int) -> None:
        if self._portfolio_service is None:
            return
        from portfolio.exceptions import PortfolioNotFoundError

        try:
            portfolio = self._portfolio_service.get_portfolio(portfolio_id)
        except PortfolioNotFoundError as exc:
            raise ValidationFailedError(f"portfolio {portfolio_id} not found") from exc
        if portfolio.owner != owner_email:
            raise PermissionDeniedError(f"portfolio {portfolio_id} does not belong to this user")

    def _validate_watchlist_ownership(self, owner_email: str, watchlist_id: int) -> None:
        if self._watchlist_service is None:
            return
        from watchlist.exceptions import WatchlistNotFoundError

        try:
            watchlist = self._watchlist_service.get_watchlist(watchlist_id)
        except WatchlistNotFoundError as exc:
            raise ValidationFailedError(f"watchlist {watchlist_id} not found") from exc
        if watchlist.owner != owner_email:
            raise PermissionDeniedError(f"watchlist {watchlist_id} does not belong to this user")
