"""Public URLs for a pharmacy's site. With TENANT_SUBDOMAINS on (needs a custom domain with wildcard DNS) each pharmacy lives at
https://<slug>.<PLATFORM_BASE_DOMAIN>; otherwise it is served by path under FRONTEND_URL (the default on *.onrender.com)."""
from django.conf import settings


def site_url(slug: str, path: str = "") -> str:
    path = ("/" + path.lstrip("/")) if path else ""
    if settings.TENANT_SUBDOMAINS:
        return f"https://{slug}.{settings.PLATFORM_BASE_DOMAIN}{path}"
    return f"{settings.FRONTEND_URL.rstrip('/')}/pharmacy/{slug}{path}"
