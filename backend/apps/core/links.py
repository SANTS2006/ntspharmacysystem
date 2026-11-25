"""Public URLs for a pharmacy's site: https://<host>/<slug>/... (path-based; one hostname for the whole platform)."""
from django.conf import settings


def site_url(slug: str, path: str = "") -> str:
    path = ("/" + path.lstrip("/")) if path else ""
    return f"{settings.FRONTEND_URL.rstrip('/')}/{slug}{path}"
