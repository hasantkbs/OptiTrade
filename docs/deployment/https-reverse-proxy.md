# HTTPS reverse proxy (SERVER STEP 5)

Topology: `Internet -> nginx (:80/:443) -> api:8000 (internal only) -> Postgres/Redis (internal only)`.

## Required environment (project root `.env`)

| Variable | Required for | Notes |
|---|---|---|
| `DOMAIN` | `proxy`, `certbot` | Real, DNS-resolvable domain, e.g. `api.example.com`. Defaults to `localhost` only so unrelated `docker compose up api postgres` commands don't fail to interpolate - never usable as a real value. |
| `FEATURE_STORE_POSTGRES_PASSWORD` | `postgres`, `api` | Unchanged from SERVER STEP 1. |

## Required environment (`backend/.env`)

| Variable | Notes |
|---|---|
| `ENVIRONMENT=production` | Required (SERVER STEP 3) - also disables `/docs`, `/redoc`, `/openapi.json`. |
| `USERS_JWT_SECRET` | Required when `ENVIRONMENT=production`, >= 32 characters (SERVER STEP 3). |
| `ALLOWED_HOSTS` | Optional. Set to `DOMAIN`'s value once known, to enable `TrustedHostMiddleware`. |
| `ALLOWED_ORIGINS` | Optional, CORS. Only relevant for a browser-based client - the iOS app doesn't send `Origin`. |

## Ports

Only **80** and **443** are published (the `proxy` service). `api` (`:8000`), `postgres` (`:5432`), and `redis` (`:6379`) are internal-network-only in `docker-compose.yml` - never change this for a production deployment. `docker-compose.override.yml` re-exposes `api`/`redis` to `127.0.0.1` for local development only and must not be deployed to production (see that file's own header).

## Issuing the certificate

Once `DOMAIN` has real DNS pointed at this host and ports 80/443 are reachable from the internet:

```bash
docker compose --profile certbot run --rm certbot certonly \
  --webroot -w /var/www/certbot -d "$DOMAIN" \
  --email you@example.com --agree-tos --no-eff-email
docker compose restart proxy
```

## Automatic renewal

```bash
docker compose --profile certbot up -d certbot
```

Runs `certbot renew` every 12 hours in a loop (standard minimal pattern - no additional scheduler). After a renewal, reload nginx to pick up the new certificate:

```bash
docker compose exec proxy nginx -s reload
```

There is no automated reload trigger in this step (would need a sidecar watching the cert directory) - add that as an operator cron entry (e.g. `0 3 * * * cd /path/to/OptiTrade && docker compose exec proxy nginx -s reload`), or as a later step if it becomes a real pain point.

## What this step does NOT do

- Does not obtain a real certificate in this environment - there is no real `DOMAIN`/DNS to issue one against. `nginx/templates/default.conf.template` references the standard certbot path (`/etc/letsencrypt/live/${DOMAIN}/`); `proxy` will not serve HTTPS until an operator actually runs the issuance command above against a real domain.
- Does not configure host-level firewall rules. If the deployment host has `ufw`/`iptables`/a cloud security-group, restricting inbound traffic to 80/443 (and SSH) is an operator action outside this repository.
- Does not add PostgreSQL backups, an admin panel, or any change to Continuous Learning/Research Lab - out of scope for this step.
