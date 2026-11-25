"""Run the test-suite against a REAL PostgreSQL instead of SQLite:   pytest --ds=config.settings_test_pg
Uses the pip-installable embedded server `pixeltable-pgserver` (dev dependency; no Docker, no system install). It starts a throw-away cluster in
.pgdata_test/ (git-ignored) and keeps it alive for the pytest process. Never points at Neon or any shared database."""
import os
from pathlib import Path

from .settings_test import *  # noqa: F401,F403
from .settings_test import BASE_DIR

import pixeltable_pgserver  # noqa: E402

_server = pixeltable_pgserver.get_server(Path(os.environ.get("PG_TEST_DATA", BASE_DIR / ".pgdata_test")), cleanup_mode="stop")
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "postgres", "USER": "postgres", "PASSWORD": "", "HOST": "127.0.0.1",
                         "PORT": str(_server.get_uri().rsplit(":", 1)[1].split("/")[0]), "ATOMIC_REQUESTS": True, "CONN_MAX_AGE": 0}}
