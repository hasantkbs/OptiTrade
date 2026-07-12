"""
Alembic async migration environment.

Run migrations:
  alembic upgrade head          # apply all pending migrations
  alembic downgrade -1          # roll back one migration
  alembic revision --autogenerate -m "description"  # generate new migration

DATABASE_URL is read from the environment, not hardcoded.
"""
import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make the backend package importable from the alembic/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Pull DATABASE_URL from environment (overrides alembic.ini placeholder)
_db_url = os.getenv("DATABASE_URL", "")
if _db_url:
    context.config.set_main_option("sqlalchemy.url", _db_url)

# Set up Python logging from alembic.ini
if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

# Import models so autogenerate can detect schema changes
from db.models import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates SQL without connecting.
    Useful for reviewing migration SQL before applying.
    """
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live database using the asyncpg driver."""
    connectable = async_engine_from_config(
        context.config.get_section(context.config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
