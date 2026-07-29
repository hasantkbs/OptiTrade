"""OptiTrade User & Organization Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class UsersConfig:
    """Runtime settings for the User & Organization Platform."""

    # JWT / sessions
    jwt_secret: str = "insecure-development-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expires_seconds: int = 15 * 60
    refresh_token_expires_seconds: int = 30 * 24 * 60 * 60
    password_reset_token_expires_seconds: int = 60 * 60
    invitation_expires_seconds: int = 7 * 24 * 60 * 60
    pbkdf2_iterations: int = 260_000

    # Redis session cache
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    session_cache_ttl_seconds: int = 300

    # Organizations / quotas
    default_max_members: int = 10
    default_max_teams: int = 5
    default_max_portfolios: int = 20
    default_max_watchlists: int = 20
    default_max_api_keys: int = 10

    @classmethod
    def from_env(cls) -> "UsersConfig":
        load_dotenv()
        return cls(
            jwt_secret=os.getenv("USERS_JWT_SECRET", "insecure-development-secret-change-me"),
            jwt_algorithm=os.getenv("USERS_JWT_ALGORITHM", "HS256"),
            access_token_expires_seconds=int(os.getenv("USERS_ACCESS_TOKEN_EXPIRES_SECONDS", str(15 * 60))),
            refresh_token_expires_seconds=int(
                os.getenv("USERS_REFRESH_TOKEN_EXPIRES_SECONDS", str(30 * 24 * 60 * 60))
            ),
            password_reset_token_expires_seconds=int(
                os.getenv("USERS_PASSWORD_RESET_TOKEN_EXPIRES_SECONDS", str(60 * 60))
            ),
            invitation_expires_seconds=int(os.getenv("USERS_INVITATION_EXPIRES_SECONDS", str(7 * 24 * 60 * 60))),
            pbkdf2_iterations=int(os.getenv("USERS_PBKDF2_ITERATIONS", "260000")),
            redis_host=os.getenv("USERS_REDIS_HOST", os.getenv("FEATURE_STORE_REDIS_HOST", "localhost")),
            redis_port=int(os.getenv("USERS_REDIS_PORT", os.getenv("FEATURE_STORE_REDIS_PORT", "6379"))),
            redis_db=int(os.getenv("USERS_REDIS_DB", os.getenv("FEATURE_STORE_REDIS_DB", "0"))),
            session_cache_ttl_seconds=int(os.getenv("USERS_SESSION_CACHE_TTL_SECONDS", "300")),
            default_max_members=int(os.getenv("USERS_DEFAULT_MAX_MEMBERS", "10")),
            default_max_teams=int(os.getenv("USERS_DEFAULT_MAX_TEAMS", "5")),
            default_max_portfolios=int(os.getenv("USERS_DEFAULT_MAX_PORTFOLIOS", "20")),
            default_max_watchlists=int(os.getenv("USERS_DEFAULT_MAX_WATCHLISTS", "20")),
            default_max_api_keys=int(os.getenv("USERS_DEFAULT_MAX_API_KEYS", "10")),
        )
