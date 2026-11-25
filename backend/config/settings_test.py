"""Test settings. Tests must NEVER touch a real/cloud database, even if a developer .env contains Neon credentials."""
from .settings import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:", "ATOMIC_REQUESTS": True}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
BREVO_API_KEY = ""
SECURE_SSL_REDIRECT = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {**REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "login": "10000/min", "sensitive": "10000/min", "verify": "10000/min", "public_write": "10000/hour"}}
FIELD_ENCRYPTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="  # test-only Fernet key
BACKUP_STORAGE = "local-ok"
BACKUP_ENCRYPTION_KEY = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="  # test-only Fernet key
BACKUP_ALLOW_RESTORE = True
BACKUP_MIN_KEEP = 1
# Never upload to Cloudinary/R2 or send real mail/payments from tests, even when the developer .env holds real credentials.
import tempfile as _tempfile  # noqa: E402
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": _tempfile.mkdtemp(prefix="pharma_test_media_")}},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
CLOUDINARY_CLOUD_NAME = CLOUDINARY_API_KEY = CLOUDINARY_API_SECRET = ""
MONIME_API_KEY = MONIME_SPACE_ID = MONIME_WEBHOOK_SECRET = ""
ADMIN_ENABLED = True
