"""
OptiTrade — Database Package
=============================
Provides async SQLAlchemy 2.x infrastructure for PostgreSQL / TimescaleDB.

Modules:
  models     — ORM table definitions
  session    — async engine + session factory (lazy, optional)
  repository — pure CRUD functions (no HTTP coupling)

The database is OPTIONAL.  If DATABASE_URL is not set, all repository
functions return no-ops rather than raising.  This keeps the API fully
functional in development environments without PostgreSQL.
"""
