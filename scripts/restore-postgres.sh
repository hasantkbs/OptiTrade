#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# OptiTrade — PostgreSQL logical restore (SERVER STEP 6).
#
# Manual, deliberate operator action - never run automatically by any
# service or scheduler. Restores a backup produced by backup-postgres.sh
# into the database named by FEATURE_STORE_POSTGRES_DB (same connection
# env vars as every other service).
#
# Usage (from inside the `backup` container, or any container/host with
# psql/pg_dump and network access to `postgres`):
#   sh restore-postgres.sh /backups/optitrade-optitrade-20260101T000000Z.sql.gz
#
# This does NOT drop or recreate the target database - pg_dump's default
# (non---clean) output is a sequence of CREATE statements for a database
# assumed empty. Restoring into a database that already has the same
# tables will fail loudly on the first conflicting CREATE rather than
# silently overwriting anything; that failure is the correct, safe
# default for this script. An operator restoring into a database that
# already has data must explicitly decide how to handle that (a fresh
# disposable database, as in this step's own restore test, is the common
# case) - this script does not make that decision for them.
# ──────────────────────────────────────────────────────────────────────────────
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 <backup-file.sql.gz>" >&2
    exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
    echo "[restore-postgres] not found: $BACKUP_FILE" >&2
    exit 1
fi

echo "[restore-postgres] restoring $BACKUP_FILE into db=$FEATURE_STORE_POSTGRES_DB host=$FEATURE_STORE_POSTGRES_HOST"

gunzip -c "$BACKUP_FILE" | PGPASSWORD="$FEATURE_STORE_POSTGRES_PASSWORD" psql \
    -h "$FEATURE_STORE_POSTGRES_HOST" \
    -p "$FEATURE_STORE_POSTGRES_PORT" \
    -U "$FEATURE_STORE_POSTGRES_USER" \
    -d "$FEATURE_STORE_POSTGRES_DB" \
    --set ON_ERROR_STOP=on

echo "[restore-postgres] done"
