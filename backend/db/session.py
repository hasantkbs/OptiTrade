"""
Async SQLAlchemy engine + session factory.

Design
------
- Lazy initialization: the engine is created on first use, not at import time.
- Optional: if DATABASE_URL is not set, get_session_factory() returns None and
  all callers must handle None gracefully.
- One engine per process (singleton). Each uvicorn worker gets its own pool.
- Pool settings are conservative; tune via env vars for production.
"""
import logging
import os
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None

DATABASE_URL: str = os.getenv("DATABASE_URL", "")


def get_engine() -> Optional[AsyncEngine]:
    global _engine
    if _engine is not None:
        return _engine
    if not DATABASE_URL:
        return None
    _engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
    )
    logger.info("PostgreSQL async engine created (pool_size=%s).", os.getenv("DB_POOL_SIZE", "5"))
    return _engine


def get_session_factory() -> Optional[async_sessionmaker]:
    global _session_factory
    if _session_factory is not None:
        return _session_factory
    engine = get_engine()
    if engine is None:
        return None
    _session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return _session_factory


async def get_db() -> AsyncGenerator[Optional[AsyncSession], None]:
    """FastAPI dependency — yields an AsyncSession or None when DB is unavailable."""
    factory = get_session_factory()
    if factory is None:
        yield None
        return
    async with factory() as session:
        yield session


def is_db_available() -> bool:
    return bool(DATABASE_URL)


async def dispose_engine() -> None:
    """Call during application shutdown to close all pool connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("PostgreSQL engine disposed.")
