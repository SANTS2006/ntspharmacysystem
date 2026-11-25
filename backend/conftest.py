import os

os.environ.setdefault("DJANGO_DEBUG", "true")
# Tests must NEVER touch a real/cloud database (a developer .env may hold Neon credentials): force in-memory SQLite.
os.environ["DATABASE_URL"] = "sqlite://:memory:"
os.environ["REDIS_URL"] = ""
os.environ["BREVO_API_KEY"] = ""
os.environ.setdefault("EMAIL_BACKEND", "django.core.mail.backends.locmem.EmailBackend")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache
    cache.clear()
    yield
