"""Django settings. All secrets/config come from environment variables (see ENVIRONMENT_VARIABLES.md)."""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me-0123456789abcdef" if DEBUG else None)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default="")  # set automatically by Render
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

PLATFORM_NAME = env("PLATFORM_NAME", default="NTS Pharmacy System")
PLATFORM_BASE_DOMAIN = env("PLATFORM_BASE_DOMAIN", default="localhost")
FRONTEND_URL = env("FRONTEND_URL", default=env("RENDER_EXTERNAL_URL", default="http://localhost:5173"))  # same origin as the API when served by Django

if not DEBUG and ("localhost" in FRONTEND_URL or "127.0.0.1" in FRONTEND_URL):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("FRONTEND_URL must be the public https URL in production: every emailed link is built from it.")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.tenants",
    "apps.accounts",
    "apps.audit",
    "apps.notifications", "apps.website",
    "apps.billing",
    "apps.medicines",
    "apps.inventory",
    "apps.procurement",
    "apps.prescriptions",
    "apps.sales",
    "apps.shop",
    "apps.payments",
    "apps.accounting",
    "apps.hr",
    "apps.payroll",
    "apps.engagement",
    "apps.delivery",
    "apps.reporting",
    "apps.backups",
    "storages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.TenantResolutionMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.backups.middleware.MaintenanceMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

# --- Database: PostgreSQL (Neon) via DATABASE_URL. SQLite only as a local/dev/test fallback. ---
# All data lives in Neon PostgreSQL: there is deliberately NO local-database fallback (tests override DATABASES in settings_test).
if not env("DATABASE_URL", default="") and not env.bool("DJANGO_ALLOW_SQLITE", default=False):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("DATABASE_URL (the Neon PostgreSQL connection string) is required.")
DATABASES = {"default": env.db("DATABASE_URL", default="sqlite:///:memory:")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
if DATABASES["default"]["ENGINE"].endswith("postgresql"):
    # Neon's pooled endpoint is PgBouncer in transaction mode: keep connections short-lived.
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = env("DB_SSLMODE", default="require")
    if env.bool("DB_USE_POOL", default=False):  # psycopg connection pool (Django 5.1+). Do not combine with Neon's PgBouncer endpoint unless you know you need both.
        DATABASES["default"]["OPTIONS"]["pool"] = {"min_size": env.int("DB_POOL_MIN", default=2), "max_size": env.int("DB_POOL_MAX", default=10)}
        DATABASES["default"]["CONN_MAX_AGE"] = 0
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis (cache, throttling, channels, celery). Falls back to local memory when unset. ---
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache", "LOCATION": REDIS_URL, "KEY_PREFIX": "pharma", "TIMEOUT": 300,
                          "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient", "SOCKET_CONNECT_TIMEOUT": 3, "SOCKET_TIMEOUT": 3,
                                      "CONNECTION_POOL_KWARGS": {"max_connections": env.int("REDIS_MAX_CONNECTIONS", default=50), "retry_on_timeout": True},
                                      "IGNORE_EXCEPTIONS": False}}}  # a Redis outage must be loud: throttling and maintenance flags depend on it
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer",
                                  "CONFIG": {"hosts": [REDIS_URL]}}}
    CELERY_BROKER_URL = REDIS_URL
    CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)  # true on hosts without a worker (e.g. Render free): tasks run inline
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CELERY_BROKER_URL = "memory://"
    CELERY_TASK_ALWAYS_EAGER = True  # dev only; production must set REDIS_URL

# --- Auth ---
AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_MAX_FAILED_ATTEMPTS = env.int("LOGIN_MAX_FAILED_ATTEMPTS", default=5)
LOGIN_LOCKOUT_MINUTES = env.int("LOGIN_LOCKOUT_MINUTES", default=15)
TEMP_CREDENTIAL_TTL_HOURS = env.int("TEMP_CREDENTIAL_TTL_HOURS", default=72)
INVITATION_TTL_HOURS = env.int("INVITATION_TTL_HOURS", default=72)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.TenantAwareJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.accounts.permissions.IsAuthenticatedAndSettled"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend",
                                "rest_framework.filters.SearchFilter", "rest_framework.filters.OrderingFilter"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle",
                                 "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "300/min", "login": "10/min", "sensitive": "5/min", "public_write": "10/hour", "verify": "10/min", "payment_refresh": "30/min"},
}
SPECTACULAR_SETTINGS = {"TITLE": f"{PLATFORM_NAME} API", "VERSION": "1.0.0", "SERVE_INCLUDE_SCHEMA": False}

# --- Security ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[FRONTEND_URL])
CORS_ALLOW_HEADERS = ["accept", "authorization", "content-type", "x-tenant-slug", "idempotency-key"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[FRONTEND_URL])
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# --- i18n / static / media ---
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"  # local development only; production uploads go to Cloudinary (see STORAGES below)

# --- Single-service hosting: Django serves the built React app (frontend/dist copied to backend/frontend_dist by build.sh) ---
FRONTEND_DIST = BASE_DIR / "frontend_dist"
if FRONTEND_DIST.exists():
    WHITENOISE_ROOT = FRONTEND_DIST  # /assets/*, /logo.webp, /favicon.png ...


def _whitenoise_headers(headers, path, url):
    headers["X-Content-Type-Options"] = "nosniff"
    if str(url).endswith(".html"):
        headers["Cache-Control"] = "no-store"
        headers["Content-Security-Policy"] = SPA_CSP


WHITENOISE_ADD_HEADERS_FUNCTION = _whitenoise_headers
WHITENOISE_MAX_AGE = 31536000 if not DEBUG else 0  # Vite fingerprints asset names
ADMIN_ENABLED = env.bool("DJANGO_ADMIN_ENABLED", default=DEBUG)  # the Django admin is not used by the product: off in production unless enabled
# CSP for the single-page app: scripts only from this origin; images may come from Cloudinary; API + WebSocket on this origin.
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"
# Google is allowed only for platform-admin sign-in and for the branch maps.
SPA_CSP = ("default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style; "
           "frame-src https://www.google.com https://maps.google.com https://accounts.google.com; img-src 'self' data: blob: https://res.cloudinary.com; "
           "font-src 'self' data:; connect-src 'self' wss: ws://localhost:* ws://127.0.0.1:* https://accounts.google.com/gsi/; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")

# --- Email: console in dev; Brevo backend is added in Phase 2 ---
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
BREVO_API_KEY = env("BREVO_API_KEY", default="")
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL", default="")  # must be a sender/domain verified in Brevo
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=BREVO_SENDER_EMAIL or "no-reply@localhost")  # set => emails go through Brevo
PLATFORM_WHATSAPP_NUMBER = env("PLATFORM_WHATSAPP_NUMBER", default="")  # digits only, e.g. 23277000000
PLATFORM_CONTACT_EMAIL = env("PLATFORM_CONTACT_EMAIL", default="")
PRESCRIPTION_FILE_MAX_BYTES = 5 * 1024 * 1024
TERMS_VERSION = env("TERMS_VERSION", default="2026-01")
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
EMAIL_CODE_TTL_MINUTES = env.int("EMAIL_CODE_TTL_MINUTES", default=15)
EMAIL_CODE_RESEND_SECONDS = env.int("EMAIL_CODE_RESEND_SECONDS", default=60)
EMAIL_CODE_MAX_ATTEMPTS = env.int("EMAIL_CODE_MAX_ATTEMPTS", default=5)
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")  # Fernet key for stored provider secrets (required when DEBUG is off)
MONIME_API_BASE = env("MONIME_API_BASE", default="https://api.monime.io")
LOGO_MAX_BYTES = 2 * 1024 * 1024

LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")}}

# Email uniqueness is per-tenant via UniqueConstraint (see accounts.User.Meta), not globally.
# drf_spectacular.W001/W002 only describe incomplete OpenAPI docs for plain APIViews (no serializer classes); they are not runtime or security problems
# and made every `check` / deploy log 400+ lines long. The schema is still generated at /api/schema/.
SILENCED_SYSTEM_CHECKS = ["auth.E003", "drf_spectacular.W001", "drf_spectacular.W002"]

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "reconcile-pending-payments": {"task": "apps.payments.tasks.reconcile_all", "schedule": crontab(minute="*/10")},
    "daily-stock-alerts": {"task": "apps.inventory.tasks.send_stock_alerts", "schedule": crontab(hour=6, minute=0)},
}


# --- Backups & object storage (Cloudflare R2 is S3-compatible). Backups and media use DIFFERENT buckets. ---
R2_ACCOUNT_ID = env("R2_ACCOUNT_ID", default="")
R2_ACCESS_KEY_ID = env("R2_ACCESS_KEY_ID", default="")
R2_SECRET_ACCESS_KEY = env("R2_SECRET_ACCESS_KEY", default="")
R2_BACKUP_BUCKET = env("R2_BACKUP_BUCKET", default="") or env("R2_BUCKET", default="")
R2_MEDIA_BUCKET = env("R2_MEDIA_BUCKET", default="")
BACKUP_STORAGE = env("BACKUP_STORAGE", default="r2" if (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BACKUP_BUCKET) else "local")  # "r2" in production
BACKUP_LOCAL_DIR = env("BACKUP_LOCAL_DIR", default=str(BASE_DIR / "backups_local"))  # development only
BACKUP_ENCRYPTION_KEY = env("BACKUP_ENCRYPTION_KEY", default="")  # Fernet key, separate from FIELD_ENCRYPTION_KEY; losing it makes every backup unreadable
BACKUP_PREFIX = env("BACKUP_PREFIX", default="db-backups")
BACKUP_RETENTION_DAYS = env.int("BACKUP_RETENTION_DAYS", default=30)
BACKUP_MIN_KEEP = env.int("BACKUP_MIN_KEEP", default=3)
BACKUP_SCHEDULE_HOURS = env.int("BACKUP_SCHEDULE_HOURS", default=6)  # this is also the RPO target (see BACKUP_AND_RECOVERY.md)
BACKUP_MAX_BYTES = env.int("BACKUP_MAX_BYTES", default=1_000_000_000)
BACKUP_ALLOW_RESTORE = env.bool("BACKUP_ALLOW_RESTORE", default=False)  # restore is off unless deliberately enabled
RESTORE_APPROVAL_MINUTES = env.int("RESTORE_APPROVAL_MINUTES", default=60)

# --- Uploaded files: Cloudinary (public images via CDN, clinical/HR documents as authenticated assets). R2 is used for backups only. ---
CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME", default="")
CLOUDINARY_API_KEY = env("CLOUDINARY_API_KEY", default="")
CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET", default="")
if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    STORAGES = {
        "default": {"BACKEND": "apps.core.storage.CloudinaryStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

CELERY_BEAT_SCHEDULE["scheduled-backup"] = {"task": "apps.backups.tasks.scheduled_backup", "schedule": crontab(minute=0, hour=f"*/{max(1, BACKUP_SCHEDULE_HOURS)}")}
CELERY_BEAT_SCHEDULE["purge-expired-backups"] = {"task": "apps.backups.tasks.purge_expired", "schedule": crontab(hour=3, minute=30)}

# --- Monime (live mobile money). ONE platform-wide Monime space, configured only through the environment (never from the UI). ---
MONIME_ACCESS_TOKEN = env("MONIME_ACCESS_TOKEN", default="") or env("MONIME_API_KEY", default="")
MONIME_SPACE_ID = env("MONIME_SPACE_ID", default="")
MONIME_WEBHOOK_SECRET = env("MONIME_WEBHOOK_SECRET", default="")
