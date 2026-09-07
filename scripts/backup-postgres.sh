#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# OptiTrade — PostgreSQL logical backup (SERVER STEP 6).
#
# Runs inside the `backup` service (docker-compose.yml, postgres:17 image -
# already has pg_dump, no separate image needed). Credentials come from the
# same FEATURE_STORE_POSTGRES_* environment variables every other service
# already uses - nothing new to configure, nothing hardcoded.
#
# Writes a gzip-compressed pg_dump to $BACKUP_DIR (the dedicated
# optitrade-postgres-backups volume - NOT the Postgres data directory
# itself, and NOT the git repository), then deletes backups in that same
# directory older than $RETENTION_DAYS. Never touches anything outside
# $BACKUP_DIR.
# ──────────────────────────────────────────────────────────────────────────────
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/optitrade-${FEATURE_STORE_POSTGRES_DB}-${TIMESTAMP}.sql.gz"

# A full logical dump includes password hashes and other user PII - owner
# read/write only, both for the directory and (via umask, applied to the
# gzip output file below) every backup file this script creates.
umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

echo "[backup-postgres] starting: db=$FEATURE_STORE_POSTGRES_DB host=$FEATURE_STORE_POSTGRES_HOST -> $FILE"

PGPASSWORD="$FEATURE_STORE_POSTGRES_PASSWORD" pg_dump \
    -h "$FEATURE_STORE_POSTGRES_HOST" \
    -p "$FEATURE_STORE_POSTGRES_PORT" \
    -U "$FEATURE_STORE_POSTGRES_USER" \
    -d "$FEATURE_STORE_POSTGRES_DB" \
    --no-owner --no-privileges \
    | gzip > "$FILE.tmp"

# Atomic rename - a reader (or the retention pass below) never observes a
# partially-written dump.
mv "$FILE.tmp" "$FILE"

echo "[backup-postgres] wrote $(du -h "$FILE" | cut -f1) to $FILE"

DELETED=$(find "$BACKUP_DIR" -name 'optitrade-*.sql.gz' -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[backup-postgres] retention: deleted $DELETED backup(s) older than ${RETENTION_DAYS}d"
fi

echo "[backup-postgres] done"
