"""OptiTrade User & Organization Platform — configuration."""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# A hardcoded, publicly-known JWT secret (this file is committed to
# source control) is a full authentication bypass - anyone who reads
# this repository can forge a valid access token for any user_id. If
# USERS_JWT_SECRET isn't set, generate a real random secret once per
# process instead of ever falling back to a fixed string. It's memoized
# here (not regenerated per UsersConfig()/from_env() call) so every
# token created and verified within the SAME process keeps working -
# it just doesn't survive a restart, and is never shared between
# processes, which is the whole point: no operator can ever be
# unknowingly running with a secret an attacker already knows.
_ephemeral_jwt_secret: "str | None" = None


def _get_or_generate_ephemeral_jwt_secret() -> str:
    global _ephemeral_jwt_secret
    if _ephemeral_jwt_secret is None:
        _ephemeral_jwt_secret = secrets.token_urlsafe(64)
        logger.warning(
            "USERS_JWT_SECRET ortam degiskeni ayarlanmamis - bu process icin rastgele, gecici bir JWT "
            "secret'i uretildi. Bu secret process yeniden baslatildiginda degisir (o ana kadar verilmis "
            "tum access/refresh token'lari gecersiz olur) ve baska bir process ile paylasilmaz. "
            "Production'da mutlaka USERS_JWT_SECRET ortam degiskenini ayarlayin."
        )
    return _ephemeral_jwt_secret


@dataclass(frozen=True)
class UsersConfig:
    """Runtime settings for the User & Organization Platform."""

    # JWT / sessions
    jwt_secret: str = field(default_factory=_get_or_generate_ephemeral_jwt_secret)
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
            jwt_secret=os.getenv("USERS_JWT_SECRET") or _get_or_generate_ephemeral_jwt_secret(),
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
