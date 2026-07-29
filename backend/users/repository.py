"""
OptiTrade User & Organization Platform — persistence.

Self-contained Postgres access (its own connection pool, not
`research_lab.base_repository.PostgresRepositoryBase`), matching the
convention `decision_engine/repository.py`, `portfolio/repository.py`,
and `watchlist/repository.py` already independently use.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Iterator, List, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.config import FeatureStoreConfig
from users.exceptions import UserPlatformPersistenceError
from users.models import (
    APIKey,
    APIKeyScope,
    APIKeyUsageRecord,
    AuditAction,
    AuditLogEntry,
    DeviceInfo,
    Invitation,
    InvitationStatus,
    LoginHistoryEntry,
    Membership,
    Organization,
    OrganizationQuotas,
    PasswordResetToken,
    Role,
    Session,
    Team,
    TeamMembership,
    User,
    UserPreferences,
    Theme,
)

logger = logging.getLogger(__name__)

_MODULE = "users.repository"
_COMPONENT = "users"

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users_users (
        id BIGSERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name VARCHAR(255) NOT NULL,
        is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL,
        last_login_at TIMESTAMPTZ
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users_organizations (
        id BIGSERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        owner_user_id BIGINT NOT NULL REFERENCES users_users (id),
        quotas JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users_teams (
        id BIGSERIAL PRIMARY KEY,
        organization_id BIGINT NOT NULL REFERENCES users_organizations (id),
        name VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users_memberships (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users_users (id),
        organization_id BIGINT NOT NULL REFERENCES users_organizations (id),
        role VARCHAR(32) NOT NULL,
        joined_at TIMESTAMPTZ NOT NULL,
        invited_by BIGINT,
        UNIQUE (user_id, organization_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users_team_memberships (
        id BIGSERIAL PRIMARY KEY,
        team_id BIGINT NOT NULL REFERENCES users_teams (id),
        user_id BIGINT NOT NULL REFERENCES users_users (id),
        added_at TIMESTAMPTZ NOT NULL,
        UNIQUE (team_id, user_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users_invitations (
        id BIGSERIAL PRIMARY KEY,
        organization_id BIGINT NOT NULL REFERENCES users_organizations (id),
        team_id BIGINT,
        email VARCHAR(255) NOT NULL,
        role VARCHAR(32) NOT NULL,
        invited_by BIGINT NOT NULL,
        token_hash VARCHAR(128) NOT NULL,
        status VARCHAR(16) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_users_invitations_org ON users_invitations (organization_id);",
    """
    CREATE TABLE IF NOT EXISTS users_sessions (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users_users (id),
        refresh_token_hash VARCHAR(128) NOT NULL,
        device JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ,
        last_used_at TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_users_sessions_user ON users_sessions (user_id);",
    "CREATE INDEX IF NOT EXISTS ix_users_sessions_token_hash ON users_sessions (refresh_token_hash);",
    """
    CREATE TABLE IF NOT EXISTS users_login_history (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT,
        email VARCHAR(255) NOT NULL,
        success BOOLEAN NOT NULL,
        failure_reason VARCHAR(255),
        device JSONB NOT NULL,
        occurred_at TIMESTAMPTZ NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_users_login_history_user ON users_login_history (user_id, occurred_at DESC);",
    """
    CREATE TABLE IF NOT EXISTS users_password_reset_tokens (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users_users (id),
        token_hash VARCHAR(128) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        used_at TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_users_password_reset_tokens_hash ON users_password_reset_tokens (token_hash);",
    """
    CREATE TABLE IF NOT EXISTS users_api_keys (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users_users (id),
        organization_id BIGINT,
        name VARCHAR(255) NOT NULL,
        key_prefix VARCHAR(16) NOT NULL,
        key_hash VARCHAR(128) NOT NULL,
        scope VARCHAR(16) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ,
        revoked_at TIMESTAMPTZ,
        last_used_at TIMESTAMPTZ,
        rotated_from_id BIGINT
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_users_api_keys_user ON users_api_keys (user_id);",
    "CREATE INDEX IF NOT EXISTS ix_users_api_keys_hash ON users_api_keys (key_hash);",
    """
    CREATE TABLE IF NOT EXISTS users_api_key_usage (
        id BIGSERIAL PRIMARY KEY,
        api_key_id BIGINT NOT NULL REFERENCES users_api_keys (id),
        endpoint VARCHAR(255) NOT NULL,
        status_code INTEGER NOT NULL,
        occurred_at TIMESTAMPTZ NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_users_api_key_usage_key ON users_api_key_usage (api_key_id, occurred_at DESC);",
    """
    CREATE TABLE IF NOT EXISTS users_preferences (
        user_id BIGINT PRIMARY KEY REFERENCES users_users (id),
        theme VARCHAR(16) NOT NULL,
        language VARCHAR(16) NOT NULL,
        notification_settings JSONB NOT NULL,
        dashboard_layout JSONB NOT NULL,
        default_portfolio_id BIGINT,
        default_watchlist_id BIGINT,
        updated_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users_audit_log (
        id BIGSERIAL PRIMARY KEY,
        actor_user_id BIGINT,
        organization_id BIGINT,
        action VARCHAR(32) NOT NULL,
        target VARCHAR(255) NOT NULL DEFAULT '',
        details JSONB NOT NULL,
        ip_address VARCHAR(64),
        occurred_at TIMESTAMPTZ NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_users_audit_log_lookup ON users_audit_log (organization_id, occurred_at DESC);",
]


class UsersRepository:
    def __init__(self, config: Optional[FeatureStoreConfig] = None, minconn: int = 1, maxconn: int = 5) -> None:
        self._config = config or FeatureStoreConfig.from_env()
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn, maxconn, host=self._config.postgres_host, port=self._config.postgres_port,
            dbname=self._config.postgres_db, user=self._config.postgres_user, password=self._config.postgres_password,
        )
        with self._connection() as conn, conn, conn.cursor() as cur:
            for statement in _SCHEMA_STATEMENTS:
                cur.execute(statement)

    @contextmanager
    def _connection(self) -> Iterator["psycopg2.extensions.connection"]:
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    # ── Users ────────────────────────────────────────────────────────────

    def save_user(self, user: User) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users_users
                        (email, password_hash, display_name, is_email_verified, is_active, created_at, last_login_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """,
                    (
                        user.email, user.password_hash, user.display_name, user.is_email_verified, user.is_active,
                        user.created_at, user.last_login_at,
                    ),
                )
                user_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_user", exc, started_at, email=user.email)
            raise UserPlatformPersistenceError(f"failed to save user: {exc}") from exc
        self._log_success("save_user", started_at, user_id=user_id)
        return user_id

    def get_user(self, user_id: int) -> Optional[User]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_users WHERE email = %s", (email.strip().lower(),))
            row = cur.fetchone()
        return self._row_to_user(row) if row else None

    def update_user(self, user: User) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users_users
                SET password_hash = %s, display_name = %s, is_email_verified = %s, is_active = %s,
                    last_login_at = %s
                WHERE id = %s
                """,
                (
                    user.password_hash, user.display_name, user.is_email_verified, user.is_active,
                    user.last_login_at, user.id,
                ),
            )

    # ── Organizations ────────────────────────────────────────────────────

    def save_organization(self, organization: Organization) -> int:
        started_at = time.perf_counter()
        try:
            with self._connection() as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users_organizations (name, owner_user_id, quotas, created_at)
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (
                        organization.name, organization.owner_user_id, organization.quotas.model_dump_json(),
                        organization.created_at,
                    ),
                )
                organization_id = cur.fetchone()[0]
        except psycopg2.Error as exc:
            self._log_error("save_organization", exc, started_at, name=organization.name)
            raise UserPlatformPersistenceError(f"failed to save organization: {exc}") from exc
        self._log_success("save_organization", started_at, organization_id=organization_id)
        return organization_id

    def get_organization(self, organization_id: int) -> Optional[Organization]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_organizations WHERE id = %s", (organization_id,))
            row = cur.fetchone()
        return self._row_to_organization(row) if row else None

    def list_organizations_for_user(self, user_id: int) -> List[Organization]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT o.* FROM users_organizations o
                JOIN users_memberships m ON m.organization_id = o.id
                WHERE m.user_id = %s ORDER BY o.created_at
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_organization(row) for row in rows]

    def update_organization(self, organization: Organization) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE users_organizations SET name = %s, owner_user_id = %s, quotas = %s WHERE id = %s",
                (organization.name, organization.owner_user_id, organization.quotas.model_dump_json(), organization.id),
            )

    def delete_organization(self, organization_id: int) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users_team_memberships WHERE team_id IN (SELECT id FROM users_teams WHERE organization_id = %s)", (organization_id,))
            cur.execute("DELETE FROM users_teams WHERE organization_id = %s", (organization_id,))
            cur.execute("DELETE FROM users_memberships WHERE organization_id = %s", (organization_id,))
            cur.execute("DELETE FROM users_invitations WHERE organization_id = %s", (organization_id,))
            cur.execute("DELETE FROM users_organizations WHERE id = %s", (organization_id,))

    # ── Teams ────────────────────────────────────────────────────────────

    def save_team(self, team: Team) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users_teams (organization_id, name, created_at) VALUES (%s, %s, %s) RETURNING id",
                (team.organization_id, team.name, team.created_at),
            )
            return cur.fetchone()[0]

    def get_team(self, team_id: int) -> Optional[Team]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_teams WHERE id = %s", (team_id,))
            row = cur.fetchone()
        return self._row_to_team(row) if row else None

    def list_teams(self, organization_id: int) -> List[Team]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users_teams WHERE organization_id = %s ORDER BY created_at", (organization_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_team(row) for row in rows]

    def delete_team(self, team_id: int) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users_team_memberships WHERE team_id = %s", (team_id,))
            cur.execute("DELETE FROM users_teams WHERE id = %s", (team_id,))

    def add_team_member(self, membership: TeamMembership) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_team_memberships (team_id, user_id, added_at) VALUES (%s, %s, %s)
                ON CONFLICT (team_id, user_id) DO UPDATE SET added_at = users_team_memberships.added_at
                RETURNING id
                """,
                (membership.team_id, membership.user_id, membership.added_at),
            )
            return cur.fetchone()[0]

    def remove_team_member(self, team_id: int, user_id: int) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users_team_memberships WHERE team_id = %s AND user_id = %s", (team_id, user_id))

    def list_team_members(self, team_id: int) -> List[TeamMembership]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_team_memberships WHERE team_id = %s ORDER BY added_at", (team_id,))
            rows = cur.fetchall()
        return [
            TeamMembership(id=row["id"], team_id=row["team_id"], user_id=row["user_id"], added_at=row["added_at"])
            for row in rows
        ]

    # ── Memberships ──────────────────────────────────────────────────────

    def save_membership(self, membership: Membership) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_memberships (user_id, organization_id, role, joined_at, invited_by)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, organization_id) DO UPDATE SET role = EXCLUDED.role
                RETURNING id
                """,
                (membership.user_id, membership.organization_id, membership.role.value, membership.joined_at,
                 membership.invited_by),
            )
            return cur.fetchone()[0]

    def get_membership(self, user_id: int, organization_id: int) -> Optional[Membership]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users_memberships WHERE user_id = %s AND organization_id = %s",
                (user_id, organization_id),
            )
            row = cur.fetchone()
        return self._row_to_membership(row) if row else None

    def list_memberships(self, organization_id: int) -> List[Membership]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users_memberships WHERE organization_id = %s ORDER BY joined_at", (organization_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_membership(row) for row in rows]

    def delete_membership(self, user_id: int, organization_id: int) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM users_memberships WHERE user_id = %s AND organization_id = %s",
                (user_id, organization_id),
            )

    # ── Invitations ──────────────────────────────────────────────────────

    def save_invitation(self, invitation: Invitation) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_invitations
                    (organization_id, team_id, email, role, invited_by, token_hash, status, created_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    invitation.organization_id, invitation.team_id, invitation.email, invitation.role.value,
                    invitation.invited_by, invitation.token_hash, invitation.status.value, invitation.created_at,
                    invitation.expires_at,
                ),
            )
            return cur.fetchone()[0]

    def get_invitation(self, invitation_id: int) -> Optional[Invitation]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_invitations WHERE id = %s", (invitation_id,))
            row = cur.fetchone()
        return self._row_to_invitation(row) if row else None

    def get_invitation_by_token_hash(self, token_hash: str) -> Optional[Invitation]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_invitations WHERE token_hash = %s", (token_hash,))
            row = cur.fetchone()
        return self._row_to_invitation(row) if row else None

    def list_invitations(self, organization_id: int) -> List[Invitation]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users_invitations WHERE organization_id = %s ORDER BY created_at DESC",
                (organization_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_invitation(row) for row in rows]

    def update_invitation_status(self, invitation_id: int, status: InvitationStatus) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE users_invitations SET status = %s WHERE id = %s", (status.value, invitation_id))

    # ── Sessions ─────────────────────────────────────────────────────────

    def save_session(self, session: Session) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_sessions
                    (user_id, refresh_token_hash, device, created_at, expires_at, revoked_at, last_used_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    session.user_id, session.refresh_token_hash, session.device.model_dump_json(),
                    session.created_at, session.expires_at, session.revoked_at, session.last_used_at,
                ),
            )
            return cur.fetchone()[0]

    def get_session(self, session_id: int) -> Optional[Session]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
        return self._row_to_session(row) if row else None

    def get_session_by_token_hash(self, token_hash: str) -> Optional[Session]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_sessions WHERE refresh_token_hash = %s", (token_hash,))
            row = cur.fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, user_id: int) -> List[Session]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users_sessions WHERE user_id = %s ORDER BY created_at DESC", (user_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_session(row) for row in rows]

    def update_session(self, session: Session) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users_sessions
                SET refresh_token_hash = %s, revoked_at = %s, last_used_at = %s, expires_at = %s
                WHERE id = %s
                """,
                (session.refresh_token_hash, session.revoked_at, session.last_used_at, session.expires_at,
                 session.id),
            )

    # ── Login history ────────────────────────────────────────────────────

    def save_login_history(self, entry: LoginHistoryEntry) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_login_history (user_id, email, success, failure_reason, device, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    entry.user_id, entry.email, entry.success, entry.failure_reason, entry.device.model_dump_json(),
                    entry.occurred_at,
                ),
            )
            return cur.fetchone()[0]

    def list_login_history(self, user_id: int, limit: int = 50) -> List[LoginHistoryEntry]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users_login_history WHERE user_id = %s ORDER BY occurred_at DESC LIMIT %s",
                (user_id, limit),
            )
            rows = cur.fetchall()
        return [
            LoginHistoryEntry(
                id=row["id"], user_id=row["user_id"], email=row["email"], success=row["success"],
                failure_reason=row["failure_reason"], device=DeviceInfo(**row["device"]), occurred_at=row["occurred_at"],
            )
            for row in rows
        ]

    # ── Password reset tokens ────────────────────────────────────────────

    def save_password_reset_token(self, token: PasswordResetToken) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_password_reset_tokens (user_id, token_hash, created_at, expires_at, used_at)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (token.user_id, token.token_hash, token.created_at, token.expires_at, token.used_at),
            )
            return cur.fetchone()[0]

    def get_password_reset_token_by_hash(self, token_hash: str) -> Optional[PasswordResetToken]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_password_reset_tokens WHERE token_hash = %s", (token_hash,))
            row = cur.fetchone()
        if row is None:
            return None
        return PasswordResetToken(
            id=row["id"], user_id=row["user_id"], token_hash=row["token_hash"], created_at=row["created_at"],
            expires_at=row["expires_at"], used_at=row["used_at"],
        )

    def mark_password_reset_token_used(self, token_id: int, used_at) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE users_password_reset_tokens SET used_at = %s WHERE id = %s", (used_at, token_id))

    # ── API keys ─────────────────────────────────────────────────────────

    def save_api_key(self, api_key: APIKey) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_api_keys
                    (user_id, organization_id, name, key_prefix, key_hash, scope, created_at, expires_at,
                     revoked_at, last_used_at, rotated_from_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    api_key.user_id, api_key.organization_id, api_key.name, api_key.key_prefix, api_key.key_hash,
                    api_key.scope.value, api_key.created_at, api_key.expires_at, api_key.revoked_at,
                    api_key.last_used_at, api_key.rotated_from_id,
                ),
            )
            return cur.fetchone()[0]

    def get_api_key(self, api_key_id: int) -> Optional[APIKey]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_api_keys WHERE id = %s", (api_key_id,))
            row = cur.fetchone()
        return self._row_to_api_key(row) if row else None

    def get_api_key_by_hash(self, key_hash: str) -> Optional[APIKey]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_api_keys WHERE key_hash = %s", (key_hash,))
            row = cur.fetchone()
        return self._row_to_api_key(row) if row else None

    def list_api_keys(self, user_id: int) -> List[APIKey]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_api_keys WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
            rows = cur.fetchall()
        return [self._row_to_api_key(row) for row in rows]

    def update_api_key(self, api_key: APIKey) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE users_api_keys SET revoked_at = %s, last_used_at = %s WHERE id = %s",
                (api_key.revoked_at, api_key.last_used_at, api_key.id),
            )

    def save_api_key_usage(self, record: APIKeyUsageRecord) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_api_key_usage (api_key_id, endpoint, status_code, occurred_at)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (record.api_key_id, record.endpoint, record.status_code, record.occurred_at),
            )
            return cur.fetchone()[0]

    def list_api_key_usage(self, api_key_id: int, limit: int = 100) -> List[APIKeyUsageRecord]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users_api_key_usage WHERE api_key_id = %s ORDER BY occurred_at DESC LIMIT %s",
                (api_key_id, limit),
            )
            rows = cur.fetchall()
        return [
            APIKeyUsageRecord(
                id=row["id"], api_key_id=row["api_key_id"], endpoint=row["endpoint"],
                status_code=row["status_code"], occurred_at=row["occurred_at"],
            )
            for row in rows
        ]

    # ── Preferences ──────────────────────────────────────────────────────

    def save_preferences(self, preferences: UserPreferences) -> None:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_preferences
                    (user_id, theme, language, notification_settings, dashboard_layout, default_portfolio_id,
                     default_watchlist_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                    SET theme = EXCLUDED.theme, language = EXCLUDED.language,
                        notification_settings = EXCLUDED.notification_settings,
                        dashboard_layout = EXCLUDED.dashboard_layout,
                        default_portfolio_id = EXCLUDED.default_portfolio_id,
                        default_watchlist_id = EXCLUDED.default_watchlist_id,
                        updated_at = EXCLUDED.updated_at
                """,
                (
                    preferences.user_id, preferences.theme.value, preferences.language,
                    json.dumps(preferences.notification_settings), json.dumps(preferences.dashboard_layout),
                    preferences.default_portfolio_id, preferences.default_watchlist_id, preferences.updated_at,
                ),
            )

    def get_preferences(self, user_id: int) -> Optional[UserPreferences]:
        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users_preferences WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return UserPreferences(
            user_id=row["user_id"], theme=Theme(row["theme"]), language=row["language"],
            notification_settings=row["notification_settings"], dashboard_layout=row["dashboard_layout"],
            default_portfolio_id=row["default_portfolio_id"], default_watchlist_id=row["default_watchlist_id"],
            updated_at=row["updated_at"],
        )

    # ── Audit log ────────────────────────────────────────────────────────

    def save_audit_entry(self, entry: AuditLogEntry) -> int:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_audit_log
                    (actor_user_id, organization_id, action, target, details, ip_address, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    entry.actor_user_id, entry.organization_id, entry.action.value, entry.target,
                    json.dumps(entry.details), entry.ip_address, entry.occurred_at,
                ),
            )
            return cur.fetchone()[0]

    def list_audit_log(
        self, organization_id: Optional[int] = None, actor_user_id: Optional[int] = None, limit: int = 100,
    ) -> List[AuditLogEntry]:
        query = "SELECT * FROM users_audit_log WHERE 1=1"
        params: list = []
        if organization_id is not None:
            query += " AND organization_id = %s"
            params.append(organization_id)
        if actor_user_id is not None:
            query += " AND actor_user_id = %s"
            params.append(actor_user_id)
        query += " ORDER BY occurred_at DESC LIMIT %s"
        params.append(limit)

        with self._connection() as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
        return [
            AuditLogEntry(
                id=row["id"], actor_user_id=row["actor_user_id"], organization_id=row["organization_id"],
                action=AuditAction(row["action"]), target=row["target"], details=row["details"],
                ip_address=row["ip_address"], occurred_at=row["occurred_at"],
            )
            for row in rows
        ]

    # ── Internals ────────────────────────────────────────────────────────

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

    @staticmethod
    def _row_to_user(row: dict) -> User:
        return User(
            id=row["id"], email=row["email"], password_hash=row["password_hash"], display_name=row["display_name"],
            is_email_verified=row["is_email_verified"], is_active=row["is_active"], created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        )

    @staticmethod
    def _row_to_organization(row: dict) -> Organization:
        return Organization(
            id=row["id"], name=row["name"], owner_user_id=row["owner_user_id"],
            quotas=OrganizationQuotas(**row["quotas"]), created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_team(row: dict) -> Team:
        return Team(id=row["id"], organization_id=row["organization_id"], name=row["name"], created_at=row["created_at"])

    @staticmethod
    def _row_to_membership(row: dict) -> Membership:
        return Membership(
            id=row["id"], user_id=row["user_id"], organization_id=row["organization_id"], role=Role(row["role"]),
            joined_at=row["joined_at"], invited_by=row["invited_by"],
        )

    @staticmethod
    def _row_to_invitation(row: dict) -> Invitation:
        return Invitation(
            id=row["id"], organization_id=row["organization_id"], team_id=row["team_id"], email=row["email"],
            role=Role(row["role"]), invited_by=row["invited_by"], token_hash=row["token_hash"],
            status=InvitationStatus(row["status"]), created_at=row["created_at"], expires_at=row["expires_at"],
        )

    @staticmethod
    def _row_to_session(row: dict) -> Session:
        return Session(
            id=row["id"], user_id=row["user_id"], refresh_token_hash=row["refresh_token_hash"],
            device=DeviceInfo(**row["device"]), created_at=row["created_at"], expires_at=row["expires_at"],
            revoked_at=row["revoked_at"], last_used_at=row["last_used_at"],
        )

    @staticmethod
    def _row_to_api_key(row: dict) -> APIKey:
        return APIKey(
            id=row["id"], user_id=row["user_id"], organization_id=row["organization_id"], name=row["name"],
            key_prefix=row["key_prefix"], key_hash=row["key_hash"], scope=APIKeyScope(row["scope"]),
            created_at=row["created_at"], expires_at=row["expires_at"], revoked_at=row["revoked_at"],
            last_used_at=row["last_used_at"], rotated_from_id=row["rotated_from_id"],
        )

    def ping(self) -> bool:
        with self._connection() as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def close(self) -> None:
        self._pool.closeall()
