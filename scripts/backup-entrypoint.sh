#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# OptiTrade — `backup` service entrypoint (SERVER STEP 6).
#
# Docker creates a fresh named volume root-owned; the postgres:17 image's
# own `postgres` user (uid 999, used by backup-postgres.sh's pg_dump/psql
# calls - no reason to run those as root) can't write to /backups until
# something chowns it. This container therefore starts as root (no
# `user:` override in docker-compose.yml, unlike every other permission
# decision in this project, which drops to non-root in the image itself -
# see backend/Dockerfile), fixes /backups' ownership once, then `exec`s
# into the actual backup loop as `postgres` via `gosu` (already present
# in the postgres:17 image - the same privilege-drop tool its own
# official entrypoint uses internally). `exec` matters here for the same
# reason it did for the API's own CMD (SERVER STEP 3): it replaces this
# script as PID 1 with the gosu'd process, so SIGTERM reaches the actual
# loop directly instead of an intermediate shell that won't forward it.
# ──────────────────────────────────────────────────────────────────────────────
set -eu

mkdir -p /backups
chown -R postgres:postgres /backups

exec gosu postgres sh -c '
    trap exit TERM
    while :; do
        sh /backup-postgres.sh
        sleep 24h &
        wait $!
    done
'
