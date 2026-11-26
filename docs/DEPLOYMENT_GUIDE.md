# Deployment Guide (no Docker)

> Written for a Linux VM or two behind a load balancer. **None of this has been exercised on real infrastructure**; treat the configs as starting points and test them in staging.

## Processes
| Process | Command (from `backend/`, virtualenv active) | Scale |
|---|---|---|
| Web + WebSockets (ASGI) | `daphne -b 127.0.0.1 -p 8000 config.asgi:application` (or `uvicorn config.asgi:application`) | one per CPU core, several hosts |
| Celery worker | `celery -A config worker -l info -c 4` | by queue depth (emails, reconciliation, backups) |
| Celery beat | `celery -A config beat -l info` | **exactly one** |
| Frontend | `npm ci && npm run build`, serve `frontend/dist` as static files (nginx/Cloudflare Pages); `/api`, `/ws`, `/health` proxy to the ASGI pool | |

Run `python manage.py migrate` once per release (from one host, before switching traffic) and `python manage.py collectstatic --noinput`. After a release that adds permissions run `python manage.py sync_role_permissions`.

## Required production environment
`DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `FRONTEND_URL`, `PUBLIC_API_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (Neon), **`REDIS_URL`** (without it throttling, maintenance mode, channels and Celery are per-process and wrong), `FIELD_ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY`, `BACKUP_STORAGE=r2` + `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/`R2_BACKUP_BUCKET`, `R2_MEDIA_BUCKET`, `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL`. Optional: `GOOGLE_OAUTH_CLIENT_ID`, `PLATFORM_WHATSAPP_NUMBER`, `DB_USE_POOL`. See ENVIRONMENT_VARIABLES.md.
Separate Redis logical databases (or instances) for cache, channels and the Celery broker are advisable (`redis://host:6379/0`, `/1`, `/2`); today one `REDIS_URL` serves all three, which is fine at small scale.

## Load balancing
- Stateless: authentication is JWT, so no sticky sessions are needed; WebSocket connections authenticate after connect and are served by any node through the Redis channel layer.
- Health checks: `GET /health/live/` (process up) and `GET /health/ready/` (database + cache; 503 when degraded). Take a node out of rotation on `ready` failure.
- Example nginx (TLS terminated here; adjust paths and certificates):
```nginx
upstream pharma_asgi { least_conn; server 10.0.0.11:8000 max_fails=2 fail_timeout=10s; server 10.0.0.12:8000 max_fails=2 fail_timeout=10s; keepalive 32; }
server {
  listen 443 ssl http2; server_name platform.example.com *.platform.example.com;
  root /srv/pharma/frontend/dist;
  location /api/    { proxy_pass http://pharma_asgi; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; client_max_body_size 12m; }
  location /health/ { proxy_pass http://pharma_asgi; access_log off; }
  location /ws/     { proxy_pass http://pharma_asgi; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; proxy_set_header Host $host; proxy_read_timeout 3600s; }
  location /        { try_files $uri /index.html; add_header Cache-Control "no-cache" always; }   # SPA routing
}
```
Django is configured for `X-Forwarded-Proto` (`SECURE_PROXY_SSL_HEADER`) and redirects to HTTPS when `DEBUG` is off. Never expose the ASGI port directly. Wildcard DNS (`*.platform.example.com`) supports subdomain tenants; custom domains need DNS + TLS provisioning that is **not built yet**.

## Database (Neon)
Use the **pooled** (PgBouncer) endpoint for the web processes (`CONN_MAX_AGE` defaults to 60 s) and keep migrations on the direct endpoint. `DB_USE_POOL=true` enables psycopg's own pool (Django 5.1+) when you are *not* using PgBouncer. `ATOMIC_REQUESTS` is on, so a request is one transaction. Row locks (`select_for_update`) and the conditional stock updates have only been verified on SQLite: **run the test-suite and a concurrency drill on PostgreSQL before launch** (see below).

## Redis
Cache client uses a bounded connection pool (`REDIS_MAX_CONNECTIONS`, default 50), 3 s socket timeouts, retry-on-timeout and **does not swallow errors** (throttling and maintenance flags depend on it). Provision persistence (AOF or RDB) only if you rely on the Celery broker for durable tasks; set `maxmemory-policy noeviction` on the broker instance and `allkeys-lru` on the cache instance.

## Pre-launch checklist (not yet done)
PostgreSQL test run; concurrent sale/stock test on PostgreSQL; PostgreSQL row-level security decision (design in TENANT_ARCHITECTURE.md); Brevo and Monime sandbox end-to-end; R2 backup/restore drill; load test of the WebSocket layer; dependency audit (`pip-audit`, `npm audit`); security header and CSP review for the SPA; DNS/TLS for tenants; log aggregation and alerting; secret rotation procedure.

## Hosting on Render (single service)

`render.yaml` defines a web service (Daphne: API, WebSockets and the built React app), a Celery worker with the beat scheduler, and a private Key Value (Redis).
`build.sh` builds the frontend, copies it to `backend/frontend_dist`, collects static files, and runs migrations over `DIRECT_DATABASE_URL` (Neon direct connection).

1. Push the repository to GitHub/GitLab (it is not a git repository yet: `git init`, commit, push; `.env` is git-ignored).
2. Render dashboard: New > Blueprint > select the repo. Fill every `sync: false` variable (same names as `backend/.env.example`).
3. After the first deploy set `PLATFORM_BASE_DOMAIN` to your `onrender.com` host (or custom domain). Pharmacies are reached by path (`/pharmacy/<slug>`), so no wildcard DNS is needed.
4. Run `python manage.py check_integrations` in the Render shell, then `send_test_email --to you@example.com`.
5. Monime: set `MONIME_SPACE_ID`, `MONIME_ACCESS_TOKEN` and `MONIME_WEBHOOK_SECRET` in Render, then create a webhook in Monime for `https://<host>/api/v1/webhooks/monime/` with the same secret (see PAYMENT_INTEGRATION.md).
6. Security defaults in production: HTTPS redirect + HSTS, secure cookies, strict CSP for the app, Django admin disabled (`DJANGO_ADMIN_ENABLED`), restore disabled (`BACKUP_ALLOW_RESTORE`).
