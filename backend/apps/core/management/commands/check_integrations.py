import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Read-only connectivity checks for Neon, Brevo (account lookup, sends nothing), Cloudinary, and R2. Never prints secrets."

    def handle(self, *a, **o):
        def run(name, fn):
            try:
                self.stdout.write(self.style.SUCCESS(f"OK    {name}: {fn()}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"FAIL  {name}: {type(exc).__name__}: {str(exc)[:200]}"))

        def db():
            with connection.cursor() as c:
                c.execute("select version()")
                return f"{connection.vendor} ({c.fetchone()[0][:30]})"

        def brevo():
            req = urllib.request.Request("https://api.brevo.com/v3/account", headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
                    json.loads(r.read())
            except urllib.error.HTTPError as e:  # Brevo's reason (bad key, unrecognised IP...) never contains the key
                raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None
            return f"account ok, sender={settings.DEFAULT_FROM_EMAIL}"

        def cloud():
            import cloudinary
            import cloudinary.api
            from apps.core.storage import _cloudinary
            _cloudinary()
            cloudinary.api.ping()
            return f"cloud '{settings.CLOUDINARY_CLOUD_NAME}' reachable"

        def r2():
            from apps.backups.storage import r2_client
            r2_client().head_bucket(Bucket=settings.R2_BACKUP_BUCKET)
            return f"bucket '{settings.R2_BACKUP_BUCKET}' reachable, BACKUP_STORAGE={settings.BACKUP_STORAGE}"

        def momo():
            from apps.payments import monime
            monime.check_credentials()
            hook = "set" if settings.MONIME_WEBHOOK_SECRET else "MISSING (payments then confirm only when the order or till screen is open)"
            return f"token and space accepted; webhook secret {hook}"

        run("database", db)
        run("monime", momo)
        run("brevo", brevo)
        run("cloudinary", cloud)
        run("r2", r2)
        from cryptography.fernet import Fernet
        for k in ("FIELD_ENCRYPTION_KEY", "BACKUP_ENCRYPTION_KEY"):
            run(k, lambda k=k: (Fernet(getattr(settings, k).encode()), "valid key")[1])
