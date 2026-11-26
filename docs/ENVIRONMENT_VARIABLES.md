# Environment Variables (backend `.env`)

| Variable | Default | Notes |
|---|---|---|
| DJANGO_DEBUG | false | Never true in production |
| DJANGO_SECRET_KEY | dev key only if DEBUG | Required in production, ≥32 chars |
| DJANGO_ALLOWED_HOSTS | localhost,127.0.0.1 | comma list |
| PLATFORM_NAME / PLATFORM_BASE_DOMAIN / FRONTEND_URL | NTS Pharmacy System / localhost / http://localhost:5173 | used for links and subdomain resolution |
| DATABASE_URL | local SQLite | Neon: `postgresql://user:pass@host/db?sslmode=require` |
| DB_CONN_MAX_AGE / DB_SSLMODE | 60 / require | Postgres only |
| REDIS_URL | empty | empty ⇒ in-process cache/channels, Celery eager (dev only) |
| CORS_ALLOWED_ORIGINS / CSRF_TRUSTED_ORIGINS | FRONTEND_URL | |
| JWT_ACCESS_MINUTES / JWT_REFRESH_DAYS | 15 / 7 | |
| LOGIN_MAX_FAILED_ATTEMPTS / LOGIN_LOCKOUT_MINUTES | 5 / 15 | |
| TEMP_CREDENTIAL_TTL_HOURS / INVITATION_TTL_HOURS | 72 / 72 | |
| EMAIL_BACKEND / DEFAULT_FROM_EMAIL | console / no-reply@localhost | Brevo integration lands in Phase 2 |

Planned (not yet read by code): BREVO_API_KEY, MONIME_*, GOOGLE_OAUTH_CLIENT_ID/SECRET, R2_*, WHATSAPP_NUMBER, BACKUP_ENCRYPTION_KEY.

## Added in Phases 2-9
BREVO_API_KEY, PLATFORM_WHATSAPP_NUMBER, PLATFORM_CONTACT_EMAIL, TERMS_VERSION, GOOGLE_OAUTH_CLIENT_ID, EMAIL_CODE_TTL_MINUTES / EMAIL_CODE_RESEND_SECONDS / EMAIL_CODE_MAX_ATTEMPTS,
**FIELD_ENCRYPTION_KEY** (Fernet key, required in production: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; losing it makes stored payment secrets unreadable), MONIME_API_BASE (default https://api.monime.io),
PUBLIC_API_URL (shown to pharmacy admins as the webhook base). Monime credentials are NOT environment variables: each pharmacy stores its own, encrypted, via the API.
Production needs REDIS_URL (channel layer, Celery, throttling) and a Celery worker plus beat (reconciliation and stock-alert tasks).

## Added in Phase 13
BACKUP_STORAGE (`r2` in production), BACKUP_ENCRYPTION_KEY (**required**, Fernet), BACKUP_RETENTION_DAYS (30), BACKUP_MIN_KEEP (3), BACKUP_SCHEDULE_HOURS (6), BACKUP_MAX_BYTES, BACKUP_PREFIX, BACKUP_ALLOW_RESTORE (false), RESTORE_APPROVAL_MINUTES (60), BACKUP_LOCAL_DIR (development only),
R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BACKUP_BUCKET, R2_MEDIA_BUCKET (switches uploaded files to private R2 storage), DB_USE_POOL / DB_POOL_MIN / DB_POOL_MAX, REDIS_MAX_CONNECTIONS.
