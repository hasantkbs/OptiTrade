# PostgreSQL backups (SERVER STEP 6)

## What runs

The `backup` service (`docker-compose.yml`, `postgres:17` image - already has `pg_dump`/`psql`, no separate image needed) runs `scripts/backup-postgres.sh` once immediately on start, then every 24 hours, for as long as the stack is up. It is a plain shell loop (the same minimal pattern `certbot`'s renewal loop already uses) - not a new application scheduler, and unrelated to either PostgreSQL advisory lock this backend already uses (727001 scheduler leader election, 727002 schema-init serialization).

## Backup

- **Command**: `pg_dump` (plain SQL, gzip-compressed) via `FEATURE_STORE_POSTGRES_*` - the same credentials/host every other service uses.
- **Destination**: the `optitrade-postgres-backups` named Docker volume, mounted at `/backups` in the `backup` container - deliberately **not** the Postgres data directory (`optitrade-postgres-data`) and **not** inside the git repository.
- **Filename**: `optitrade-<db>-<UTC timestamp>.sql.gz`.
- **Retention**: files older than `BACKUP_RETENTION_DAYS` (default **7**) are deleted after each successful backup - only inside `/backups`, nothing else is ever touched. Override via the project-root `.env`: `BACKUP_RETENTION_DAYS=14`.

## Restore

```bash
# List available backups
docker compose exec backup ls -la /backups

# Restore a specific one into FEATURE_STORE_POSTGRES_DB
docker compose exec backup sh /restore-postgres.sh /backups/optitrade-optitrade-20260101T000000Z.sql.gz
```

`restore-postgres.sh` does **not** drop or recreate the target database first - restoring into a database that already has the same tables will fail loudly on the first conflicting `CREATE` rather than silently overwriting data. Restoring into a fresh/disposable database (the common case - a new environment, or disaster recovery after data loss) works cleanly. See this step's own verification below for the exact tested procedure.

## Off-host disaster-recovery limitation

**This is a local-Docker-volume backup, not disaster recovery.** If the host itself is lost (disk failure, instance termination, accidental volume deletion), the `optitrade-postgres-backups` volume is lost along with `optitrade-postgres-data` - a local backup does not protect against that. Copying backups off-host (e.g. to S3/GCS/an object store, or another machine) on some schedule is a **required operator action** for real disaster-recovery coverage; it is outside what this repository/Docker Compose setup can do on its own; a simple starting point is a cron job on the host running `docker cp` or `docker compose exec backup cat /backups/<file>` piped to an off-host destination after each backup.

## Verification (this step)

Tested against the project's own disposable Postgres volume only - see the SERVER STEP 6 final report for exact commands/output. Never run against an external or pre-existing database.
